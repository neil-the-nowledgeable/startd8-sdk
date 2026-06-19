# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-openapi-contract
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

import json
from typing import Any

ROUTE_MANIFEST: tuple[tuple[str, str], ...] = (
    ("DELETE", "/placeordersession/{item_id}"),
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/placeordersession/"),
    ("GET", "/placeordersession/{item_id}"),
    ("PATCH", "/placeordersession/{item_id}"),
    ("POST", "/placeordersession/"),
)


OPENAPI_SPEC: dict[str, Any] = json.loads(
    '''{
  "components": {
    "schemas": {
      "PlaceOrderSessionCreate": {
        "properties": {
          "email": {
            "type": "string"
          },
          "userId": {
            "type": "string"
          }
        },
        "required": [
          "userId",
          "email"
        ],
        "type": "object"
      },
      "PlaceOrderSessionRead": {
        "properties": {
          "createdAt": {
            "format": "date-time",
            "type": "string"
          },
          "email": {
            "type": "string"
          },
          "id": {
            "type": "string"
          },
          "userId": {
            "type": "string"
          }
        },
        "required": [
          "id",
          "userId",
          "email",
          "createdAt"
        ],
        "type": "object"
      },
      "PlaceOrderSessionUpdate": {
        "properties": {
          "createdAt": {
            "format": "date-time",
            "type": "string"
          },
          "email": {
            "type": "string"
          },
          "userId": {
            "type": "string"
          }
        },
        "type": "object"
      }
    }
  },
  "info": {
    "title": "PlaceOrderSession",
    "version": "0.0.0"
  },
  "openapi": "3.0.3",
  "paths": {
    "/health": {
      "get": {
        "responses": {
          "200": {
            "description": "OK"
          }
        }
      }
    },
    "/health/live": {
      "get": {
        "responses": {
          "200": {
            "description": "OK"
          }
        }
      }
    },
    "/placeordersession/": {
      "get": {
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PlaceOrderSessionRead"
                }
              }
            },
            "description": "OK"
          }
        }
      },
      "post": {
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/PlaceOrderSessionCreate"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PlaceOrderSessionRead"
                }
              }
            },
            "description": "OK"
          }
        }
      }
    },
    "/placeordersession/{item_id}": {
      "delete": {
        "parameters": [
          {
            "in": "path",
            "name": "item_id",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "No Content"
          }
        }
      },
      "get": {
        "parameters": [
          {
            "in": "path",
            "name": "item_id",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PlaceOrderSessionRead"
                }
              }
            },
            "description": "OK"
          }
        }
      },
      "patch": {
        "parameters": [
          {
            "in": "path",
            "name": "item_id",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/PlaceOrderSessionUpdate"
              }
            }
          }
        },
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PlaceOrderSessionRead"
                }
              }
            },
            "description": "OK"
          }
        }
      }
    }
  }
}'''
)


def route_paths() -> list[str]:
    """Sorted unique paths from :data:`ROUTE_MANIFEST` (for boot-smoke)."""
    return sorted({path for _, path in ROUTE_MANIFEST})
