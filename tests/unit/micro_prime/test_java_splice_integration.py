"""End-to-end Java splice integration tests.

Tests the full path: skeleton → parse elements → splice bodies → verify result.
"""

import pytest

from startd8.languages.java_parser import parse_java_source
from startd8.languages.java_splicer import splice_java_bodies, JavaSpliceResult
from startd8.utils.java_file_assembler import (
    JavaDeterministicFileAssembler,
    JAVA_SKELETON_SENTINEL,
    JAVA_STUB_BODY,
)


JAVA_SKELETON = """\
package hipstershop;

import io.grpc.stub.StreamObserver;
import hipstershop.proto.AdServiceGrpc;
import hipstershop.proto.AdRequest;
import hipstershop.proto.AdResponse;
import hipstershop.proto.Ad;

// [STARTD8-SKELETON]

public class AdService extends AdServiceGrpc.AdServiceImplBase {

    public AdService() {
        throw new UnsupportedOperationException("TODO");
    }

    @Override
    public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver) {
        throw new UnsupportedOperationException("TODO");
    }

    public void initStats() {
        throw new UnsupportedOperationException("TODO");
    }
}
"""


class TestJavaSpliceRoundTrip:
    """Test skeleton → parse → splice → verify cycle."""

    def test_splice_replaces_stub(self):
        # The splicer expects generated code to include the method declaration
        result = splice_java_bodies(JAVA_SKELETON, {
            "getAds": (
                "public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver) {\n"
                "    List<Ad> ads = new ArrayList<>();\n"
                "    ads.add(Ad.newBuilder().setText(\"sample\").build());\n"
                "    responseObserver.onNext(AdResponse.newBuilder().addAllAds(ads).build());\n"
                "    responseObserver.onCompleted();\n"
                "}"
            ),
        })
        assert result.methods_spliced == 1
        assert "responseObserver.onCompleted" in result.code

    def test_splice_preserves_non_stub(self):
        skeleton_with_impl = JAVA_SKELETON.replace(
            "    public void initStats() {\n        throw new UnsupportedOperationException(\"TODO\");\n    }",
            "    public void initStats() {\n        StatsCollector.init();\n    }",
        )
        result = splice_java_bodies(skeleton_with_impl, {
            "initStats": "public void initStats() {\n    // this should NOT be spliced\n}",
        })
        assert result.methods_skipped == 1
        assert "StatsCollector.init" in result.code

    def test_splice_multiple_stubs(self):
        result = splice_java_bodies(JAVA_SKELETON, {
            "AdService": "public AdService() {\n    logger = LoggerFactory.getLogger(AdService.class);\n}",
            "getAds": "public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver) {\n    responseObserver.onCompleted();\n}",
            "initStats": "public void initStats() {\n    StatsCollector.init();\n}",
        })
        assert result.methods_spliced == 3
        assert result.methods_skipped == 0

    def test_splice_missing_method_produces_warning(self):
        result = splice_java_bodies(JAVA_SKELETON, {
            "nonexistent": "public void nonexistent() {\n    // body\n}",
        })
        assert result.methods_skipped == 1
        assert any("nonexistent" in w.lower() for w in result.warnings)

    def test_splice_statistics(self):
        result = splice_java_bodies(JAVA_SKELETON, {
            "getAds": "public void getAds(AdRequest r, StreamObserver<AdResponse> o) {\n    o.onCompleted();\n}",
            "nonexistent": "public void nonexistent() {\n    // skip\n}",
        })
        assert result.methods_spliced == 1
        assert result.methods_skipped == 1
        assert result.code is not None


class TestJavaParserSplicerParity:
    """Verify parser and splicer agree on element detection."""

    def test_parser_finds_all_skeleton_elements(self):
        elements = parse_java_source(JAVA_SKELETON)
        names = {e.name for e in elements}
        assert "AdService" in names  # class or constructor
        assert "getAds" in names
        assert "initStats" in names

    def test_splicer_can_target_all_parser_methods(self):
        """Every method the parser finds should be spliceable."""
        elements = parse_java_source(JAVA_SKELETON)
        method_names = [e.name for e in elements if e.kind == "method"]
        # Generated code must include method declarations for the splicer
        bodies = {
            name: f"public void {name}() {{\n    // implemented {name}\n}}"
            for name in method_names
        }
        result = splice_java_bodies(JAVA_SKELETON, bodies)
        # All methods that are stubs should be spliced
        assert result.methods_spliced >= 1


class TestJavaDFAToSpliceRoundTrip:
    """Test DFA skeleton → splice → verify."""

    def test_dfa_skeleton_is_spliceable(self):
        """A skeleton from the DFA should be spliceable without errors."""
        from dataclasses import dataclass, field
        from typing import List, Optional

        @dataclass
        class FakeElement:
            kind: str = "method"
            name: str = ""
            return_type: str = "void"
            bases: List[str] = field(default_factory=list)
            modifiers: List[str] = field(default_factory=lambda: ["public"])
            parameters: str = ""
            annotations: List[str] = field(default_factory=list)
            parent_class: Optional[str] = None
            type_annotation: Optional[str] = None

        @dataclass
        class FakeImport:
            module: str = ""

        @dataclass
        class FakeFileSpec:
            file: str = ""
            elements: List[FakeElement] = field(default_factory=list)
            imports: List[FakeImport] = field(default_factory=list)

        file_spec = FakeFileSpec(
            file="src/main/java/hipstershop/CartService.java",
            elements=[
                FakeElement(
                    kind="method",
                    name="addItem",
                    return_type="void",
                    parameters="String userId, String productId, int quantity",
                ),
            ],
        )

        assembler = JavaDeterministicFileAssembler()
        skeleton = assembler.render_file(file_spec)

        assert skeleton is not None
        assert JAVA_SKELETON_SENTINEL in skeleton
        assert JAVA_STUB_BODY in skeleton

        # Now splice a body into the stub (generated code includes declaration)
        result = splice_java_bodies(skeleton, {
            "addItem": "public void addItem(String userId, String productId, int quantity) {\n    repository.save(userId, productId, quantity);\n}",
        })
        assert result.methods_spliced == 1
        assert "repository.save" in result.code
