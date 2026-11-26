-- Enforce the binary and textual formats produced by the application hash functions.
-- Existing rows are validated without rewriting or deleting identity/session data.

ALTER TABLE user_identities
    ADD CONSTRAINT user_identities_lookup_hash_sha256_length
    CHECK (octet_length(identity_lookup_hash) = 32) NOT VALID;
ALTER TABLE user_identities
    VALIDATE CONSTRAINT user_identities_lookup_hash_sha256_length;

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_lookup_hash_sha256_length
    CHECK (octet_length(identity_lookup_hash) = 32) NOT VALID;
ALTER TABLE otp_challenges
    VALIDATE CONSTRAINT otp_challenges_lookup_hash_sha256_length;

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_code_hash_sha256_length
    CHECK (octet_length(code_hash) = 32) NOT VALID;
ALTER TABLE otp_challenges
    VALIDATE CONSTRAINT otp_challenges_code_hash_sha256_length;

ALTER TABLE auth_sessions
    ADD CONSTRAINT auth_sessions_token_hash_sha256_hex
    CHECK (token_hash ~ '^[0-9a-f]{64}$') NOT VALID;
ALTER TABLE auth_sessions
    VALIDATE CONSTRAINT auth_sessions_token_hash_sha256_hex;

ALTER TABLE auth_sessions
    ADD CONSTRAINT auth_sessions_replacement_hash_sha256_hex
    CHECK (
        replaced_by_token_hash IS NULL
        OR replaced_by_token_hash ~ '^[0-9a-f]{64}$'
    ) NOT VALID;
ALTER TABLE auth_sessions
    VALIDATE CONSTRAINT auth_sessions_replacement_hash_sha256_hex;

ALTER TABLE oauth_states
    ADD CONSTRAINT oauth_states_hash_sha256_hex
    CHECK (state_hash ~ '^[0-9a-f]{64}$') NOT VALID;
ALTER TABLE oauth_states
    VALIDATE CONSTRAINT oauth_states_hash_sha256_hex;
