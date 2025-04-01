use serde::{Deserialize, Serialize};

/// Types of transformations that can be applied to tables.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TransformType {
    /// Transform a table from wide to long format
    WideToLong {
        /// Columns to use as identifier variables
        id_vars: Vec<String>,
        /// Columns to unpivot
        value_vars: Vec<String>,
        /// Name to use for the variable column
        var_name: String,
        /// Name to use for the value column
        value_name: String,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transform_type_creation() {
        let transform = TransformType::WideToLong {
            id_vars: vec!["age".to_string()],
            value_vars: vec!["male".to_string(), "female".to_string()],
            var_name: "gender".to_string(),
            value_name: "mortality_rate".to_string(),
        };

        match transform {
            TransformType::WideToLong {
                id_vars,
                value_vars,
                var_name,
                value_name,
            } => {
                assert_eq!(id_vars, vec!["age"]);
                assert_eq!(value_vars, vec!["male", "female"]);
                assert_eq!(var_name, "gender");
                assert_eq!(value_name, "mortality_rate");
            }
        }
    }
}
