// startd8 composite oracle over unmodified, vendored Perses release schemas.
package oracle

import (
	persesV1 "github.com/perses/perses/cue/model/api/v1"
	dashboard "github.com/perses/spec/cue/dashboard"
	timeSeries "github.com/perses/plugins/timeserieschart/schemas:model"
	markdown "github.com/perses/plugins/markdown/schemas:model"
	logsTable "github.com/perses/plugins/logstable/schemas:model"
	prometheusQuery "github.com/perses/plugins/prometheus/schemas/prometheus-time-series-query:model"
	lokiQuery "github.com/perses/plugins/loki/schemas/queries/loki-log-query:model"
	staticList "github.com/perses/plugins/staticlistvariable/schemas:model"
)

#PortableQuery: dashboard.#Query & ({
	kind: "TimeSeriesQuery"
	spec: plugin: prometheusQuery
} | {
	kind: "LogQuery"
	spec: plugin: lokiQuery
})

#PortablePanel: persesV1.#Panel & {
	spec: {
		plugin: timeSeries | markdown | logsTable
		queries?: [...#PortableQuery]
	}
}

#PortableVariable: dashboard.#Variable & {
	kind: "ListVariable"
	spec: plugin: staticList
}

#Dashboard: persesV1.#Dashboard & {
	spec: {
		panels: [string]: #PortablePanel
		variables?: [...#PortableVariable]
	}
}
