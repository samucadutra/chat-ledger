-- Creates the database used by the Python test suite (TEST_DATABASE_URL), so
-- the compose `db` service can back `make test` on a developer machine.
CREATE DATABASE chatledger_test OWNER chatledger;
