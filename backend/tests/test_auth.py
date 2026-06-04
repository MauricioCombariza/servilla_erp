import pytest


@pytest.mark.asyncio
async def test_login_ok(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["role"] == "administrador"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    r = await client.post("/api/auth/login", json={"username": "noexiste", "password": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client):
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "admin"
    assert data["rol"] == "administrador"


@pytest.mark.asyncio
async def test_me_without_token(client):
    r = await client.get("/api/auth/me")
    assert r.status_code in (401, 403)  # HTTPBearer devuelve 403 si no hay header


@pytest.mark.asyncio
async def test_refresh(client):
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    refresh_token = login.json()["refresh_token"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_access_token_rejected_as_refresh(client):
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    access_token = login.json()["access_token"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401
