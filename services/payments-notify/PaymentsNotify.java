// ACME Bank payments-notify: the sample service for the JVM memory exhaustion incident family (DD01).
//
// It sends payment notifications, and keeps a notification template cache that is never evicted.
// Triggering the fault makes the cache grow steadily until the container is killed. The service is
// deliberately misconfigured the way many real JVM services are: its maximum heap equals its
// container's memory limit, so the JVM's own memory pushes the container over the limit before the
// heap is full, and the kernel kills it (OOMKilled) rather than Java raising an OutOfMemoryError.
//
// Scenarios (POST /fault?scenario=...):
//   single     the cache grows until the container is killed once; it restarts clean.
//   recurring  as single, but the fault resumes after every restart, until the pod is replaced
//              (reset.yml) or POST /fault/clear is called. The marker lives in an emptyDir volume,
//              which survives container restarts but not a new pod.
//
// No dependencies: the JDK's own HTTP server and management beans. Plain HTTP on port 8080, reachable
// only from the namespaces the network policy allows (phase 08).

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class PaymentsNotify {

    private static final int MB = 1024 * 1024;
    private static final int LEAK_MB_PER_SECOND = Integer.parseInt(env("LEAK_MB_PER_SECOND", "1"));
    private static final Path RECURRING = Path.of(env("FAULT_STATE_DIR", "/var/lib/payments-notify"), "recurring");

    private static final List<byte[]> TEMPLATE_CACHE = Collections.synchronizedList(new ArrayList<>());
    private static final ScheduledExecutorService LEAK = Executors.newSingleThreadScheduledExecutor();
    private static final MemoryMXBean MEMORY = ManagementFactory.getMemoryMXBean();
    private static volatile ScheduledFuture<?> leaking;
    private static volatile String scenario = "none";

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
        server.createContext("/healthz", exchange -> respond(exchange, 200, "text/plain", "ok\n"));
        server.createContext("/metrics", exchange -> respond(exchange, 200, "text/plain; version=0.0.4", metrics()));
        server.createContext("/fault", PaymentsNotify::fault);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();
        log("INFO", "payments-notify started; max heap " + MEMORY.getHeapMemoryUsage().getMax() / MB + " MB");

        if (Files.exists(RECURRING)) {
            log("WARN", "recurring fault marker found: notification template cache growth resumes after restart");
            startLeak("recurring");
        }
    }

    private static void fault(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "text/plain", "POST only\n");
            return;
        }
        String path = exchange.getRequestURI().getPath();
        String query = String.valueOf(exchange.getRequestURI().getQuery());
        if (path.equals("/fault/clear")) {
            Files.deleteIfExists(RECURRING);
            if (leaking != null) {
                leaking.cancel(false);
                leaking = null;
            }
            TEMPLATE_CACHE.clear();
            scenario = "none";
            log("INFO", "fault cleared: cache emptied, recurring marker removed");
            respond(exchange, 200, "text/plain", "cleared\n");
        } else if (query.equals("scenario=single") || query.equals("scenario=recurring")) {
            String requested = query.substring("scenario=".length());
            if (requested.equals("recurring")) {
                Files.writeString(RECURRING, Instant.now().toString());
            }
            startLeak(requested);
            respond(exchange, 202, "text/plain", "fault started: " + requested + "\n");
        } else {
            respond(exchange, 400, "text/plain", "use POST /fault?scenario=single, ?scenario=recurring or /fault/clear\n");
        }
    }

    private static synchronized void startLeak(String requested) {
        scenario = requested;
        if (leaking != null) {
            return;
        }
        log("WARN", "notification template cache now grows by " + LEAK_MB_PER_SECOND + " MB a second and is never evicted");
        leaking = LEAK.scheduleAtFixedRate(() -> {
            byte[] entry = new byte[LEAK_MB_PER_SECOND * MB];
            Arrays.fill(entry, (byte) 1);
            TEMPLATE_CACHE.add(entry);
            int size = TEMPLATE_CACHE.size() * LEAK_MB_PER_SECOND;
            if (size % 10 == 0) {
                MemoryUsage heap = MEMORY.getHeapMemoryUsage();
                log("WARN", "NotificationTemplateCache size=" + size + "MB heap=" + heap.getUsed() * 100 / heap.getMax()
                        + "% entries are never evicted");
            }
        }, 0, 1, TimeUnit.SECONDS);
    }

    private static String metrics() {
        MemoryUsage heap = MEMORY.getHeapMemoryUsage();
        MemoryUsage nonHeap = MEMORY.getNonHeapMemoryUsage();
        long cacheBytes = (long) TEMPLATE_CACHE.size() * LEAK_MB_PER_SECOND * MB;
        return "# HELP jvm_memory_used_bytes The amount of used memory\n"
                + "# TYPE jvm_memory_used_bytes gauge\n"
                + "jvm_memory_used_bytes{area=\"heap\"} " + heap.getUsed() + "\n"
                + "jvm_memory_used_bytes{area=\"nonheap\"} " + nonHeap.getUsed() + "\n"
                + "# HELP jvm_memory_max_bytes The maximum amount of memory that can be used\n"
                + "# TYPE jvm_memory_max_bytes gauge\n"
                + "jvm_memory_max_bytes{area=\"heap\"} " + heap.getMax() + "\n"
                + "# HELP jvm_memory_committed_bytes The amount of memory committed for the JVM to use\n"
                + "# TYPE jvm_memory_committed_bytes gauge\n"
                + "jvm_memory_committed_bytes{area=\"heap\"} " + heap.getCommitted() + "\n"
                + "jvm_memory_committed_bytes{area=\"nonheap\"} " + nonHeap.getCommitted() + "\n"
                + "# HELP payments_notify_template_cache_bytes Size of the notification template cache\n"
                + "# TYPE payments_notify_template_cache_bytes gauge\n"
                + "payments_notify_template_cache_bytes " + cacheBytes + "\n"
                + "# HELP payments_notify_fault_active Whether the cache is growing (1) or not (0)\n"
                + "# TYPE payments_notify_fault_active gauge\n"
                + "payments_notify_fault_active{scenario=\"" + scenario + "\"} " + (leaking != null ? 1 : 0) + "\n";
    }

    private static void respond(HttpExchange exchange, int status, String type, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", type);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void log(String level, String message) {
        System.out.println(Instant.now() + " " + level + " payments-notify " + message);
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
