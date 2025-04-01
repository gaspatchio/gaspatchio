use serde::Deserialize;

/// Arguments for the assumption lookup plugin.
#[derive(Debug, Clone, Deserialize)]
pub struct AssumptionLookupKwargs {
    /// Name of the table to look up values from
    pub table_name: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json;

    #[test]
    fn test_kwargs_deserialization() {
        let json = r#"{"table_name": "mortality_rates"}"#;
        let kwargs: AssumptionLookupKwargs = serde_json::from_str(json).unwrap();
        assert_eq!(kwargs.table_name, "mortality_rates");
    }
}
