package dev.canopy.links;

import io.netty.util.NetUtil;
import java.net.URI;
import java.util.Locale;
import java.util.Set;

final class DestinationPolicy {
    private static final Set<String> INTERNAL_SUFFIXES = Set.of(".localhost", ".local", ".internal", ".lan", ".home.arpa");

    private DestinationPolicy() {}

    static boolean allowed(URI uri) {
        if (!("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))) return false;
        if (uri.getHost() == null) return false;
        String host = uri.getHost().toLowerCase(Locale.ROOT);
        if (host.endsWith(".")) host = host.substring(0, host.length() - 1);
        if (host.indexOf('%') >= 0) return false;
        byte[] address = NetUtil.createByteArrayFromIpAddressString(host);
        if (address != null) {
            if (address.length == 16) {
                // Only global-unicast IPv6 literals; excludes mapped IPv4, ULA, site/link-local and multicast.
                return (address[0] & 0xe0) == 0x20;
            }
            if (host.matches("(?:.*\\.)?0[0-9]+(?:\\..*)?")) return false;
            int a = address[0] & 255;
            int b = address[1] & 255;
            return !(a == 0 || a == 10 || a == 127 || a >= 224 || a == 169 && b == 254
                    || a == 172 && b >= 16 && b <= 31 || a == 192 && b == 168
                    || a == 100 && b >= 64 && b <= 127 || a == 198 && (b == 18 || b == 19));
        }
        if (!host.contains(".") || host.matches("(?:0x[0-9a-f]+|[0-9]+)(?:\\.(?:0x[0-9a-f]+|[0-9]+))*")) return false;
        for (String suffix : INTERNAL_SUFFIXES) {
            if (host.endsWith(suffix)) return false;
        }
        return true;
    }
}
