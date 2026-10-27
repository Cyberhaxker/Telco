-- Web-app accounts (bcrypt password hashes, comma-separated roles). Also created by apps/web/scripts/seed-users.mjs.
CREATE TABLE IF NOT EXISTS app_users (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(40)  NOT NULL UNIQUE,
  name          VARCHAR(80)  NOT NULL,
  password_hash VARCHAR(100) NOT NULL,
  roles         VARCHAR(120) NOT NULL DEFAULT 'viewer',
  active        TINYINT(1)   NOT NULL DEFAULT 1,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
