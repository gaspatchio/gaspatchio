from gaspatchio_core import ActuarialFrame

# scalar
data = {
    "policy_id": ["P001", "P002", "P003", "P004"],
    "age_decimal": [35.8, 42.2, 58.9, 67.1],
}
af = ActuarialFrame(data)

af.completed_age = af.age_decimal.floor()

print(af.collect())

# vector
data = {
    "policy_id": ["P001", "P002"],
    "age": [55, 38],
    "month": [[1, 2, 3, 4], [1, 2, 3, 4]],
    "policy_duration": [[9.0, 9.08, 9.16, 9.25], [5.0, 5.08, 5.16, 5.25]],
}
af = ActuarialFrame(data)

af.completed_years = af.policy_duration.floor()

print(af.collect())
