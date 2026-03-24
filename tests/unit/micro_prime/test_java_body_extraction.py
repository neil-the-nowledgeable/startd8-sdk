"""Tests for Java body extraction via brace-depth matching.

Uses java_splicer's internal functions directly to avoid loading
the full MicroPrime engine (which has heavy dependencies).
"""

import pytest

from startd8.languages.java_splicer import (
    _find_body_range,
    _find_method_declaration,
)


SAMPLE_JAVA = """\
package hipstershop;

import io.grpc.stub.StreamObserver;

public class AdService extends AdServiceGrpc.AdServiceImplBase {

    private static final Logger logger = LoggerFactory.getLogger(AdService.class);

    public AdService() {
        logger.info("AdService initialized");
    }

    @Override
    public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver) {
        List<Ad> ads = new ArrayList<>();
        ads.add(Ad.newBuilder().setText("sample").build());
        responseObserver.onNext(AdResponse.newBuilder().addAllAds(ads).build());
        responseObserver.onCompleted();
    }

    public static void main(String[] args) {
        int port = 9555;
        new AdService().start(port);
    }

    public List<String> getCategories() {
        return Collections.emptyList();
    }

    public void initStats() {
        // TODO: implement stats initialization
    }
}
"""


def _extract_body(source: str, name: str) -> str | None:
    """Extract a method/constructor body by name using splicer internals."""
    lines = source.splitlines()
    decl_line = _find_method_declaration(lines, name)
    if decl_line is None:
        return None
    body_range = _find_body_range(lines, decl_line)
    if body_range is None:
        return None
    open_line, close_line = body_range
    body_lines = lines[open_line + 1 : close_line]
    return "\n".join(body_lines)


class TestJavaBodyExtraction:
    """Verify body extraction works for Java source."""

    def test_extracts_constructor_body(self):
        body = _extract_body(SAMPLE_JAVA, "AdService")
        assert body is not None
        assert "AdService initialized" in body

    def test_extracts_method_body(self):
        body = _extract_body(SAMPLE_JAVA, "getAds")
        assert body is not None
        assert "responseObserver.onNext" in body
        assert "responseObserver.onCompleted" in body

    def test_extracts_static_main(self):
        body = _extract_body(SAMPLE_JAVA, "main")
        assert body is not None
        assert "9555" in body

    def test_extracts_generic_return_type(self):
        body = _extract_body(SAMPLE_JAVA, "getCategories")
        assert body is not None
        assert "emptyList" in body

    def test_extracts_stub_body(self):
        body = _extract_body(SAMPLE_JAVA, "initStats")
        assert body is not None
        assert "TODO" in body

    def test_nonexistent_returns_none(self):
        body = _extract_body(SAMPLE_JAVA, "nonexistentMethod")
        assert body is None

    def test_handles_nested_braces(self):
        nested = """\
public class Service {
    public void process() {
        if (condition) {
            for (int i = 0; i < 10; i++) {
                doSomething(i);
            }
        }
    }
}
"""
        body = _extract_body(nested, "process")
        assert body is not None
        assert "doSomething" in body

    def test_handles_annotated_method(self):
        annotated = """\
public class Service {
    @Override
    @Transactional
    public void save(Entity entity) {
        repository.save(entity);
    }
}
"""
        body = _extract_body(annotated, "save")
        assert body is not None
        assert "repository.save" in body

    def test_interface_method_has_no_body(self):
        interface = """\
public interface ICartStore {
    void addItem(String userId, String productId, int quantity);
}
"""
        decl = _find_method_declaration(interface.splitlines(), "addItem")
        # Interface methods may or may not be found — if found, no body range
        if decl is not None:
            body_range = _find_body_range(interface.splitlines(), decl)
            # No opening brace on interface method declaration
            assert body_range is None or body_range[0] == body_range[1]
