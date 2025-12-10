# API Key Export/Import Guide

## Overview

The startd8 SDK now supports **secure, encrypted export and import of API keys** between different startd8 instances. This allows you to:

- **Backup your API keys** in an encrypted format
- **Transfer API keys** to another computer or environment
- **Share API keys** securely with team members (when appropriate)
- **Migrate configurations** when setting up new development environments

All exports are **encrypted at rest** using industry-standard cryptography (Fernet symmetric encryption with PBKDF2 key derivation).

---

## How to Export API Keys

### Step-by-Step Instructions

1. **Launch the TUI**:
   ```bash
   startd8-tui
   # or
   python -m startd8.cli tui
   ```

2. **Navigate to API Key Management**:
   - From the main menu, select **`🔑 Manage API Keys`**

3. **Select Export Option**:
   - In the API Key Management menu, select **`📤 Export API Keys (Encrypted)`**

4. **Review Keys to Export**:
   - The TUI will show you which API keys will be exported
   - By default, ALL stored keys are exported (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)

5. **Choose Export Location**:
   - Default: `~/startd8_keys_export.enc`
   - You can specify any path you prefer
   - Example: `/path/to/backup/my_keys.enc`

6. **Set Encryption Password**:
   - Enter a **strong password** (minimum 8 characters recommended)
   - You'll need to confirm the password
   - **⚠️ IMPORTANT**: Remember this password! You'll need it to import the keys later

7. **Wait for Encryption**:
   - The TUI will encrypt your API keys (takes 1-2 seconds)
   - A success message will confirm the export

8. **Secure the Export File**:
   - The encrypted file is saved to the location you specified
   - **Keep this file secure** - it contains your encrypted API keys
   - **Delete it after importing** on the target system

### Example Export Flow

```
┌─────────────────────────────────────────────────────┐
│           Export API Keys (Encrypted)               │
├─────────────────────────────────────────────────────┤
│ This will export your stored API keys to an         │
│ encrypted file.                                     │
│                                                     │
│ ⚠️  The export file will contain your API keys!    │
│ Keep it secure and delete it after importing.      │
└─────────────────────────────────────────────────────┘

Keys to be exported:
  • ANTHROPIC_API_KEY
  • OPENAI_API_KEY

? Export file path: ~/startd8_keys_export.enc
? Set encryption password: ********
? Confirm password: ********

⚡ Encrypting and exporting...

┌─────────────────────────────────────────────────────┐
│              Export Successful                      │
├─────────────────────────────────────────────────────┤
│ ✓ API keys exported successfully!                  │
│                                                     │
│ Encrypted file saved to:                           │
│ /Users/you/startd8_keys_export.enc                 │
│                                                     │
│ To import on another system:                       │
│ 1. Copy the .enc file securely                    │
│ 2. Use 'Import API Keys' in this menu             │
│ 3. Enter the same password                        │
│                                                     │
│ ⚠️  Keep this file secure and delete after        │
│     importing!                                     │
└─────────────────────────────────────────────────────┘
```

---

## How to Import API Keys

### Step-by-Step Instructions

1. **Transfer the Export File**:
   - Copy the `.enc` file to your target system
   - Use secure methods (SCP, encrypted USB, secure cloud storage)

2. **Launch the TUI** on the target system:
   ```bash
   startd8-tui
   ```

3. **Navigate to API Key Management**:
   - Select **`🔑 Manage API Keys`**

4. **Select Import Option**:
   - Select **`📥 Import API Keys (Encrypted)`**

5. **Specify Import File**:
   - Enter the path to your `.enc` file
   - Default: `~/startd8_keys_export.enc`

6. **Enter Decryption Password**:
   - Enter the **same password** you used during export
   - If the password is incorrect, decryption will fail

7. **Choose Overwrite Behavior**:
   - If keys with the same name already exist, you can:
     - **Skip** (keep existing keys)
     - **Overwrite** (replace with imported keys)

8. **Review Import Results**:
   - The TUI shows which keys were imported
   - Which keys were skipped (if any)

9. **Test Connections**:
   - Use **`🔬 Test Agent Connections`** to verify the imported keys work

### Example Import Flow

```
┌─────────────────────────────────────────────────────┐
│           Import API Keys (Encrypted)               │
├─────────────────────────────────────────────────────┤
│ This will import API keys from an encrypted export │
│ file.                                               │
│                                                     │
│ Existing keys with the same name can be            │
│ overwritten.                                        │
└─────────────────────────────────────────────────────┘

? Import file path: ~/startd8_keys_export.enc
? Enter decryption password: ********
? Overwrite existing keys with same name? No

⚡ Decrypting and importing...

✓ Successfully imported keys:
  ✓ ANTHROPIC_API_KEY
  ✓ OPENAI_API_KEY

┌─────────────────────────────────────────────────────┐
│              Import Successful                      │
├─────────────────────────────────────────────────────┤
│ Import completed successfully!                     │
│                                                     │
│ API keys are now available for use.               │
│ You can test them with 'Test Agent Connections'.  │
└─────────────────────────────────────────────────────┘
```

---

## Security Details

### Encryption Method

The export/import system uses **military-grade encryption**:

- **Algorithm**: Fernet (symmetric encryption based on AES-128 in CBC mode)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 480,000 iterations (OWASP recommended)
- **Authentication**: Built-in message authentication (prevents tampering)
- **Salt**: Random 16-byte salt per export (prevents rainbow table attacks)

### What Gets Encrypted

The export file contains:
```json
{
  "api_keys": {
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "OPENAI_API_KEY": "sk-..."
  },
  "metadata": {
    "exported_at": "2025-12-07T18:30:00Z",
    "key_count": 2,
    "key_names": ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    "version": "1.0"
  }
}
```

All of this is encrypted before being written to the `.enc` file.

### File Permissions

- Export files are created with **restrictive permissions** (600 on Unix systems)
- Only the file owner can read/write the file
- Same security as SSH private keys

---

## Best Practices

### ✅ DO

- **Use strong passwords**: At least 12 characters, mix of letters, numbers, symbols
- **Delete export files** after importing them
- **Store exports securely**: Encrypted cloud storage, password manager, secure USB
- **Use unique passwords** for each export if creating multiple backups
- **Test imports** immediately to verify the password works

### ❌ DON'T

- **Don't commit `.enc` files** to version control (even though they're encrypted)
- **Don't share passwords** via insecure channels (plain text email, Slack, etc.)
- **Don't reuse weak passwords** like "password123"
- **Don't keep old export files** unnecessarily
- **Don't assume encryption = invincibility**: Strong password + secure storage = best security

---

## Troubleshooting

### "No API keys stored to export"

**Cause**: You don't have any API keys saved in startd8's storage.

**Solution**: 
- Set API keys first using **`🔑 Manage API Keys`** → **`Set Claude API Key`** or **`Set GPT-4 API Key`**
- Or the keys are only in environment variables (which aren't exported by default)

### "Incorrect password"

**Cause**: The password you entered doesn't match the one used during export.

**Solution**:
- Double-check your password (passwords are case-sensitive)
- Make sure you're using the correct export file
- If you've forgotten the password, you'll need to re-export from the source system

### "File not found"

**Cause**: The import file path is incorrect or the file doesn't exist.

**Solution**:
- Check the file path is correct
- Use absolute paths if relative paths aren't working
- Ensure you copied the file to the target system

### Import shows "All keys skipped"

**Cause**: Keys with the same names already exist, and you chose not to overwrite.

**Solution**:
- Run import again and choose **Yes** when asked to overwrite
- Or manually delete existing keys first in **`🔑 Manage API Keys`**

---

## Command-Line Usage (Advanced)

You can also export/import programmatically:

### Python API

```python
from pathlib import Path
from startd8.tui_improved import APIKeyManager

# Initialize manager
key_manager = APIKeyManager()

# Export
export_path = Path("~/my_keys.enc").expanduser()
password = "my_strong_password"
success = key_manager.export_keys(export_path, password)

# Import
result = key_manager.import_keys(export_path, password, overwrite=True)
print(f"Imported: {result['imported']}")
print(f"Skipped: {result['skipped']}")
```

### Using the Encryption Library Directly

```python
from startd8.security import KeyEncryption

encryptor = KeyEncryption()

# Export
api_keys = {
    'ANTHROPIC_API_KEY': 'sk-ant-...',
    'OPENAI_API_KEY': 'sk-...'
}
encrypted = encryptor.encrypt_api_keys(api_keys, "password")

# Save to file
with open("keys.enc", "w") as f:
    f.write(encrypted)

# Import
with open("keys.enc", "r") as f:
    encrypted = f.read()

package = encryptor.decrypt_api_keys(encrypted, "password")
api_keys = package['api_keys']
```

---

## FAQ

**Q: Are the API keys encrypted when stored normally (not exported)?**

A: By default, API keys in `api_keys.json` are stored in plain text with restrictive file permissions (600). The encryption is specifically for export/import. If you want keys encrypted at rest always, you can store them in your OS keychain or use environment variables.

**Q: Can I export only specific API keys?**

A: Currently, all stored keys are exported together. If you need selective export, you can:
1. Temporarily remove keys you don't want to export
2. Export
3. Re-add the removed keys

**Q: What if I lose my export password?**

A: There's no password recovery. You'll need to create a new export from the source system. Keep your password in a secure password manager!

**Q: Can I import the same export file multiple times?**

A: Yes! The import file isn't modified or deleted during import. You can use the same export to set up multiple systems.

**Q: Is this secure enough for production use?**

A: Yes, the encryption is production-grade. However:
- Use strong passwords (12+ characters)
- Store export files securely
- Delete exports when no longer needed
- Consider your organization's security policies

**Q: Can I transfer keys between different operating systems?**

A: Yes! The export format is cross-platform. You can export on macOS and import on Linux, Windows, etc.

---

## Dependencies

The encryption feature requires the `cryptography` library:

```bash
pip install cryptography>=41.0.0
```

This is automatically included in startd8's requirements.

---

## Support

If you encounter issues:

1. Check this guide's troubleshooting section
2. Verify `cryptography` is installed: `pip list | grep cryptography`
3. Check the TUI displays encryption options (if not, reinstall dependencies)
4. Run tests: `pytest tests/unit/test_encryption.py -v`

---

**Last Updated**: December 7, 2025

