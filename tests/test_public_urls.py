import socket
from unittest.mock import patch

import pytest

from nonebot_plugin_soruto_ai.core import unfurl


def test_public_destination_is_pinned_without_a_second_dns_lookup():
    addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
    with patch.object(unfurl.socket,'getaddrinfo',return_value=addresses) as resolve:
        url,headers,extensions=unfurl.public_target('https://public.example/article')
    assert url.host=='8.8.8.8'
    assert url.path=='/article'
    assert headers=={'Host':'public.example'}
    assert extensions=={'sni_hostname':'public.example'}
    resolve.assert_called_once()


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1'])
def test_nonpublic_resolutions_are_rejected(address):
    addresses=[(socket.AF_INET6 if ':' in address else socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]
    with patch.object(unfurl.socket,'getaddrinfo',return_value=addresses):
        with pytest.raises(ValueError):
            unfurl.public_target('https://untrusted.example/')
