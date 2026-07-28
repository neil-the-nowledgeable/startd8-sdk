## Do this

**Blind rotate:** spawn a Task/subagent with model
`{{reviewer_model}}` (roster index {{roster_index}}).
**Do not** run the CRP review in the current chat.

1. Pass `{{bundle_path}}` to that Task; it follows the bundle
   with filesystem write tools.
2. Task writes only the source paths listed below.
3. Task writes confirmation JSON to `{{status_writeback_path}}`
   including `reviewer_model: "{{reviewer_model}}"`.
4. Current chat runs `startd8 wloop run-next --job-id {{job_id}}`
   to verify.
