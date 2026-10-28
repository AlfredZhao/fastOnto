import base64

import pytest

from app.business_sources import BusinessSourceError, CredentialCipher, _identifier
from app.config import Settings


def settings(key: str):
    return Settings(_env_file=None, db_dsn='', db_password='', source_master_key=key)


def test_credentials_are_aead_encrypted_and_round_trip():
    key = base64.urlsafe_b64encode(b'k' * 32).decode().rstrip('=')
    cipher = CredentialCipher(settings(key))
    value = cipher.encrypt('db.example:1521/service', 'READONLY', 'not-a-real-password')
    assert 'not-a-real-password' not in value and value.startswith('v1.')
    assert cipher.decrypt(value) == {'dsn': 'db.example:1521/service', 'username': 'READONLY', 'password': 'not-a-real-password'}


def test_wrong_key_cannot_decrypt():
    first = CredentialCipher(settings(base64.urlsafe_b64encode(b'a' * 32).decode().rstrip('=')))
    second = CredentialCipher(settings(base64.urlsafe_b64encode(b'b' * 32).decode().rstrip('=')))
    with pytest.raises(BusinessSourceError): second.decrypt(first.encrypt('dsn', 'USER', 'password'))


@pytest.mark.parametrize('value', ['SH', 'SALES_2026', 'A$B#C', 'lower', 'BAD-NAME', '"QUOTED"'])
def test_oracle_identifier_profile(value):
    if value in {'SH', 'SALES_2026', 'A$B#C', 'lower'}: assert _identifier(value, 'Schema') == value.upper()
    else:
        with pytest.raises(BusinessSourceError): _identifier(value, 'Schema')
