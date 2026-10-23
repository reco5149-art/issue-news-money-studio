import socket
import pytest
import asyncio
import httpx
from app import providers as p

def test_dns_error_reports_host_without_query_secrets(monkeypatch):
 def fail(*args,**kwargs):raise socket.gaierror()
 monkeypatch.setattr(socket,"getaddrinfo",fail)
 with pytest.raises(p.ProviderError) as error:p.public_url("https://missing.example/photo?token=SECRET")
 assert error.value.code=="dns_resolution"
 assert "missing.example" in str(error.value)
 assert "SECRET" not in str(error.value)


def test_api_connection_error_identifies_service_without_url_or_header_secrets(monkeypatch):
 async def fail(self,method,url,**kwargs):
  raise httpx.ConnectError('sensitive upstream detail SECRET', request=httpx.Request(method,url))
 monkeypatch.setattr(httpx.AsyncClient,'request',fail)
 with pytest.raises(p.ProviderError) as error:
  asyncio.run(p.api('GET','https://graph.instagram.com/v24.0/private-id?access_token=SECRET',
                    headers={'Authorization':'Bearer SECRET'}))
 assert error.value.code=='external_connection'
 assert 'Instagram' in str(error.value) and 'graph.instagram.com' in str(error.value)
 assert 'ConnectError' in str(error.value)
 assert 'SECRET' not in str(error.value) and 'private-id' not in str(error.value)
