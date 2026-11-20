import pytest


@pytest.mark.asyncio
async def test_login_ok(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    # El refresh va solo en la cookie HttpOnly
    assert data.get("refresh_token") is None
    cookie = r.headers["set-cookie"]
    assert "servilla_refresh=" in cookie and "HttpOnly" in cookie and "Path=/api/auth" in cookie
    assert "SameSite=strict" in cookie
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
    refresh_token = login.cookies["servilla_refresh"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_access_token_rejected_as_refresh(client):
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    access_token = login.json()["access_token"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_y_logout_con_la_cookie():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # Cliente propio: el compartido acumula cookies de otras pruebas
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})).status_code == 200
        r = await c.post("/api/auth/refresh")
        assert r.status_code == 200 and r.json()["access_token"]
        acceso = r.json()["access_token"]
        assert (await c.post("/api/auth/logout")).status_code == 204
        assert "servilla_refresh" not in c.cookies
        assert (await c.post("/api/auth/refresh")).status_code == 401
        assert (await c.get("/api/auth/me", headers={"Authorization": f"Bearer {acceso}"})).status_code == 401
