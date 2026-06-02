// Package shop is a deliberately small but realistic Go fixture for the
// Code Observability Phase 0 spike.
//
// It contains:
//   (a) A multi-level call chain:
//         handleRequest -> buildQuery -> execSQL -> rawDBExec
//       plus a "safe" parallel path:
//         handleSafeRequest -> buildSafeQuery -> execSQLParams
//   (b) A deliberate TAINT PATH (source -> sink):
//         handleRequest reads untrusted input r.URL.Query().Get("id")
//         -> passes it to buildQuery (string concatenation into raw SQL)
//         -> execSQL -> rawDBExec   (the SQL-injection sink)
//
// The safe path uses parameterized queries and must NOT be flagged.
package shop

import (
	"database/sql"
	"fmt"
	"net/http"
)

var db *sql.DB

// handleRequest is the TAINTED entrypoint.
// SOURCE: untrusted HTTP input.
func handleRequest(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("id") // <-- TAINT SOURCE (untrusted)
	query := buildQuery(userID)       // taint flows into buildQuery
	rows := execSQL(query)            // tainted query reaches execSQL
	fmt.Fprintf(w, "rows=%v", rows)
}

// buildQuery concatenates untrusted input straight into a raw SQL string.
// This is the vulnerable transform on the taint path.
func buildQuery(id string) string {
	// VULNERABLE: raw string concatenation of untrusted `id`.
	return "SELECT * FROM users WHERE id = '" + id + "'"
}

// execSQL forwards the (tainted) query string toward the DB driver.
func execSQL(query string) int {
	return rawDBExec(query) // tainted query reaches the SINK
}

// rawDBExec is the SINK: it hands a raw, unparameterized string to the driver.
func rawDBExec(query string) int {
	rows, err := db.Query(query) // <-- TAINT SINK (raw SQL to driver)
	if err != nil {
		return 0
	}
	defer rows.Close()
	n := 0
	for rows.Next() {
		n++
	}
	return n
}

// ---------------------------------------------------------------------------
// SAFE parallel path (parameterized) — must NOT be flagged as a taint path.
// ---------------------------------------------------------------------------

// handleSafeRequest reads untrusted input but routes it through a
// parameterized query, so no raw-SQL concatenation sink is reached.
func handleSafeRequest(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("id") // untrusted, but handled safely
	query := buildSafeQuery()         // constant query, no taint
	rows := execSQLParams(query, userID)
	fmt.Fprintf(w, "rows=%v", rows)
}

// buildSafeQuery returns a constant parameterized query (no concatenation).
func buildSafeQuery() string {
	return "SELECT * FROM users WHERE id = ?"
}

// execSQLParams uses bound parameters — the safe sink.
func execSQLParams(query string, args ...interface{}) int {
	rows, err := db.Query(query, args...) // parameterized: safe
	if err != nil {
		return 0
	}
	defer rows.Close()
	return 1
}
