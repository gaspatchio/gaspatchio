


add_dimension 





analyse_table - LLM friendly table analysis 



lookup should use kwarg lookup_keys to determine the order of the keys to lookup


```python
af["CSO table"] = gs.assumption_lookup(
        sex= "Policyholder sex",
        smoking= "Policyholder smoking status",
        age= "issue_age",
        year= "year_lookup",
        table_name="mortality_vbt",
    )
```
