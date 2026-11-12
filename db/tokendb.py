TOKEN_TABLE="""CREATE TABLE refresh_tokens (
    jti TEXT PRIMARY KEY,
    username TEXT,
    expires_at TIMESTAMPZ,
    revoked BOOLEAN DEFAULT FALSE
);
"""