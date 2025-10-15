from gaspatchio_core import ActuarialFrame

# Minimal example: uppercase a status field for standardized reporting
data = {
    "policy_id": ["P1", "P2"],
    "status_raw": ["In Force", "lapsed"],
}

af = ActuarialFrame(data)

af.status_upper = af.status_raw.str.to_uppercase()

print(af.collect())
