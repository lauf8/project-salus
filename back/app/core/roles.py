PROFILE_FIELDS = (
    "is_astronaut", "is_physician", "is_psychologist", "is_nutritionist",
    "is_nurse", "is_observer", "is_mission_admin", "is_global_admin",
)
PUBLIC_PROFILE_FIELDS = PROFILE_FIELDS[:-1]
MISSION_ROLES = {"mission_admin", "astronaut", "flight_surgeon", "psychologist", "nutritionist", "nurse", "observer"}
ROLE_PROFILES = {
    "astronaut": "is_astronaut", "psychologist": "is_psychologist",
    "nutritionist": "is_nutritionist", "nurse": "is_nurse", "observer": "is_observer",
}
