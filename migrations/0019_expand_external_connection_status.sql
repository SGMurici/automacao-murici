-- Allow the fail-closed Gmail lifecycle state without truncating its value.
ALTER TABLE external_connections
    ALTER COLUMN status TYPE VARCHAR(40);
