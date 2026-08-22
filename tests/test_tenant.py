from bulwark.platform.models import Tenant, TenantRepo


def test_get_or_default_returns_configured_tenant():
    repo = TenantRepo()
    repo.upsert(Tenant(tenant="acme-eu", region_pin="europe-west4", framework="SOC2"))
    assert repo.get_or_default("acme-eu").region_pin == "europe-west4"


def test_get_or_default_falls_back_for_unknown_tenant():
    repo = TenantRepo()
    tenant = repo.get_or_default("never-configured-tenant")
    assert tenant.tenant == "never-configured-tenant"
    assert tenant.region_pin == "us-central1"


def test_region_pin_matches():
    repo = TenantRepo()
    repo.upsert(Tenant(tenant="acme-eu", region_pin="europe-west4"))
    assert repo.region_pin_matches("acme-eu", "europe-west4") is True
    assert repo.region_pin_matches("acme-eu", "us-central1") is False
