# Fix for ListResourcesRequest Error

## Error Message
```
2025-12-11 14:29:08.766 [error] Processing request of type ListResourcesRequest
```

## Root Cause
The error occurs when the MCP client requests a list of resources (`ListResourcesRequest`). FastMCP automatically enumerates all registered resources, and if an exception occurs during resource enumeration or conversion, it causes the request to fail.

## Changes Made

### 1. Enhanced Error Handling in `_find_skills()`
- Added try-except blocks around directory scanning (`rglob`)
- Added error handling for individual skill file parsing
- Returns empty list instead of raising exceptions
- Added logging for debugging

### 2. Improved Resource Handler Error Handling
- Added logging to `get_skill_resource()` to track resource access
- Enhanced error messages with traceback information
- Ensures exceptions don't propagate to FastMCP's resource manager

### 3. Wrapped `list_resources()` Method
- Added `_safe_list_resources()` wrapper around FastMCP's `list_resources()` method
- Catches exceptions during resource enumeration and conversion
- Returns empty list instead of failing
- Added comprehensive logging

### 4. Low-Level Handler Override (Attempted)
- Attempted to wrap the low-level MCP request handler
- May not be accessible depending on FastMCP's internal structure

## Testing
1. Restart the MCP server
2. Test resource listing from the MCP client
3. Check server logs for `[mcp-debug]` messages showing resource listing activity
4. Verify that skills are discoverable via `startd8_list_skills` tool

## Next Steps
If the error persists:
1. Check server logs for the full error traceback (look for `[mcp-debug]` messages)
2. Verify `STARTD8_SKILL_PATH` is set correctly
3. Ensure skill directories are readable
4. Check for permission issues on skill directories
5. Verify that the monkey-patch is working by checking logs for "list_resources called"

## Files Modified
- `startd8_mcp.py`: 
  - Added error handling to `_find_skills()` and `get_skill_resource()`
  - Added `_safe_list_resources()` wrapper
  - Attempted low-level handler override
