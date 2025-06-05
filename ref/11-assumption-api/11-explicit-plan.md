

different methods for different table types


add_dimension 


extend_to=250


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



## Explicit Dimension Option 

## Analysis

```python
import gaspatchio_core as gs

# Step 1: Analyze table structure (LLM-friendly discovery)
schema = gs.analyze_table("2015-VBT-FSM-ANB.csv")
print(schema)
# Output:
# TableSchema(
#   data_dimensions=['issue_age'],  # from CSV columns
#   value_columns=['1', '2', '3', ..., '25', 'Ult.'],  # detected wide format
#   suggested_melt_dimension='duration',  # suggested name for melted columns
#   overflow_column='Ult.',
#   format='wide'
# )

# Analyze and suggest interpolation
analysis = gs.analyze_table("lapse.csv")
print(analysis.suggest_interpolation())
# Output: "Detected sparse duration columns [1,2,5,10,15,25]. 
#          Consider linear interpolation to fill gaps."
```


## Sammple API 

```python
# Step 2: Load with explicit dimension mapping
table = gs.Table(
    name="mortality_vbt",
    source="2015-VBT-FSM-ANB.csv",
    dimensions={
        # Data dimensions (from file)
        'issue_age': 'issue_age',  # map column to dimension name or gs.DataColumn('issue_age')
        'duration': gs.MeltColumns(
            columns=['1', '2', '3', ..., '25'],  # Explicit columns
            name='duration',  # Name the melted dimension
            overflow='Ult.',  # Overflow column
            extend_to=120     # Extend overflow value from 26 to 120
        ),        
        # Categorical dimensions (added)
        'sex': gs.Constant('F'),
        'smoking': gs.Constant('SM'),
    },
    value='qx'
)

# Step 3: Extend table with new slices
table.extend(
    source="2015-VBT-MSM-ANB.csv",
    dimensions={
        'sex': gs.Constant('M'),  # Different slice
        'smoking': gs.Constant('SM'),
    }
)

# Step 4: Clear dimension-based lookup
# Lookup using kwargs - order doesn't matter, mapping is explicit
af["mortality"] = table.lookup(
    issue_age=af["issue_age"],
    duration=af["year_lookup"],
    sex=af["Policyholder sex"],
    smoking=af["Policyholder smoking status"]
)
```


```python
table = gs.Table(
    name="lapse_rates",
    source="lapse_select.csv", 
    dimensions={
        'issue_age': 'issue_age',
        'duration': gs.MeltColumns(
            columns=['1', '2', '5', '10', '15', '25'],
            fill_strategy=gs.Interpolate(
                method='linear',
                to_range=(1, 25),
                by=1  # Step size
            )
        )
    },
    value='lapse_rate'
)

# Other fill strategies
gs.MeltColumns(
    columns=['1', '2', '5', '10', '15', '25', 'Ult.'],
    fill_strategy=gs.Combined([
        gs.Interpolate(method='linear', to_range=(1, 25)),
        gs.Extend(overflow='Ult.', to_value=100)
    ])
)


# Typical select and ultimate table with interpolation needs
mortality = gs.Table(
    name="mortality_select_ultimate", 
    source="mort_select.csv",
    dimensions={
        'issue_age': 'issue_age',
        
        # Select period: interpolate between key durations
        'select_duration': gs.InterpolatedDimension(
            source_columns=['1', '2', '5', '10'],
            target_range=(1, 10),
            method='log-linear'  # Appropriate for mortality
        ),
        
        # Ultimate: just reuse the ultimate column
        'ultimate_duration': gs.MeltColumns(
            columns=['Ultimate'],
            extend_to=100  # Reuse for durations 11-100
        )
    },
    value='qx'
)

# Usage would automatically handle the interpolation
af["qx"] = mortality.lookup(
    issue_age=af["issue_age"],
    duration=af["policy_duration"]  # Automatically interpolates
)

```

### table introspection 

```python
# Inspect loaded table structure
print(table.dimensions)
# Dimensions(
#   age: DataColumn(source='issue_age'),
#   duration: MeltedDimension(columns=['1','2',...], overflow='Ult.'),
#   sex: Constant('F'),
#   smoking: Constant('SM')
# )

print(table.measures)
# ['qx']

# Get unique values for a dimension
print(table.dimension_values('sex'))
# ['F', 'M']
```
