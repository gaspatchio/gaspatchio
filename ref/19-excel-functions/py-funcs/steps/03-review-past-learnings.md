# Step 3: Review Past Learnings

## Input
- Function name from Step 1
- Behavior analysis from Step 2

## Task
Check for any existing insights or tips for this function in past learnings.

### Actions
1. Read `ref/19-excel-functions/py-funcs/19-pylearnings.md`
2. Search for mentions of {{FUNCTION_NAME}} or similar functions
3. Extract relevant patterns, gotchas, or implementation tips

## Output
Save the learnings summary to: `pyfuncs-outputs/{{FUNCTION_NAME}}_output/03-learnings-summary.yaml`

```yaml
function_name: {{FUNCTION_NAME}}
past_learnings_found: true/false
relevant_insights:
  - insight: "Description of insight"
    source: "Which function or context this came from"
    applies_to: "How this applies to {{FUNCTION_NAME}}"
similar_functions:
  - name: "SIMILAR_FUNC"
    similarity: "What patterns they share"
    implementation_notes: "What to copy/avoid"
specific_tips:
  - "Tip 1 for implementing this function"
  - "Tip 2 about common mistakes"
no_learnings_reason: "If no learnings found, explain why (new function type, etc.)"
```

## Next Step
This output feeds into Step 4: Analyze Rust Implementation