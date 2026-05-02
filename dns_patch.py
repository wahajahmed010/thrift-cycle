"""DNS patch for api.ebay.com — routes to working Akamai IPs.

eBay's api.ebay.com CNAME chain (api.ebay.com → global-api.ebaycdn.net) 
currently has no A records. This patches socket.getaddrinfo to resolve
api.ebay.com to api.g.ebay.com's Akamai IPs, which serve the same SSL cert.
"""
import socket

_ORIGINAL_GETADDRINFO = socket.getaddrinfo

# Working Akamai IPs
API_EBAY_IPS = ['209.140.129.1', '66.211.166.2']
SVCS_EBAY_IPS = ['2.23.7.19', '2.23.7.48']

def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == 'api.ebay.com':
        results = []
        for ip in API_EBAY_IPS:
            results.append((socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)))
        return results
    if host == 'svcs.ebay.com':
        results = []
        for ip in SVCS_EBAY_IPS:
            results.append((socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)))
        return results
    return _ORIGINAL_GETADDRINFO(host, port, family, type, proto, flags)

socket.getaddrinfo = _patched_getaddrinfo
