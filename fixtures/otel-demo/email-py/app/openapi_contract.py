# GENERATED from prisma/schema.prisma (+ api.yaml) — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-openapi-contract
# Source of truth: the Prisma schema and the API surface overlay.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102
# api-sha256: d278eb94eee389795506130e5f8738e41ce4fa7b4f59d578df65ca8fea94e626

from __future__ import annotations

import json
from typing import Any

ROUTE_MANIFEST: tuple[tuple[str, str], ...] = (
    ("DELETE", "/orderconfirmation/{item_id}"),
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/orderconfirmation/"),
    ("GET", "/orderconfirmation/{item_id}"),
    ("PATCH", "/orderconfirmation/{item_id}"),
    ("POST", "/orderconfirmation/"),
    ("POST", "/send_order_confirmation"),
)


OPENAPI_SPEC: dict[str, Any] = json.loads(
    '''{
  "components": {
    "schemas": {
      "OrderConfirmationCreate": {
        "properties": {
          "email": {
            "type": "string"
          },
          "orderId": {
            "type": "string"
          }
        },
        "required": [
          "orderId",
          "email"
        ],
        "type": "object"
      },
      "OrderConfirmationRead": {
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
          "orderId": {
            "type": "string"
          }
        },
        "required": [
          "id",
          "orderId",
          "email",
          "createdAt"
        ],
        "type": "object"
      },
      "OrderConfirmationRequest": {
        "properties": {
          "order": {
            "properties": {
              "email": {
                "type": "string"
              },
              "order_id": {
                "type": "string"
              }
            },
            "type": "object"
          }
        },
        "required": [
          "order"
        ],
        "type": "object"
      },
      "OrderConfirmationUpdate": {
        "properties": {
          "createdAt": {
            "format": "date-time",
            "type": "string"
          },
          "email": {
            "type": "string"
          },
          "orderId": {
            "type": "string"
          }
        },
        "type": "object"
      }
    }
  },
  "info": {
    "title": "OrderConfirmation",
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
    "/orderconfirmation/": {
      "get": {
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OrderConfirmationRead"
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
                "$ref": "#/components/schemas/OrderConfirmationCreate"
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
                  "$ref": "#/components/schemas/OrderConfirmationRead"
                }
              }
            },
            "description": "OK"
          }
        }
      }
    },
    "/orderconfirmation/{item_id}": {
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
                  "$ref": "#/components/schemas/OrderConfirmationRead"
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
                "$ref": "#/components/schemas/OrderConfirmationUpdate"
              }
            }
          }
        },
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OrderConfirmationRead"
                }
              }
            },
            "description": "OK"
          }
        }
      }
    },
    "/send_order_confirmation": {
      "post": {
        "operationId": "sendOrderConfirmation",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/OrderConfirmationRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Confirmation accepted"
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
