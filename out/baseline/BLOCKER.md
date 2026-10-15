Baseline stopped.

Provider/response failure; no further batches scheduled: HTTP Error 400: Bad Request {
  "error": {
    "code": 400,
    "message": "Invalid value at 'generation_config.response_format.text.mime_type' (type.googleapis.com/google.ai.generativelanguage.v1beta.TextResponseFormat.MimeType), \"application/json\"",
    "status": "INVALID_ARGUMENT",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.BadRequest",
        "fieldViolations": [
          {
            "field": "generation_config.response_format.text.mime_type",
            "description": "Invalid value at 'generation_config.response_format.text.mime_type' (type.googleapis.com/google.ai.generativelanguage.v1beta.TextResponseFormat.MimeType), \"application/json\""
          }
        ]
      }
    ]
  }
}


Saved call records include any returned usage. No automatic retry or model substitution was attempted.

Recovery in progress: API reference https://ai.google.dev/api/generate-content?authuser=01&hl=en names APPLICATION_JSON as the REST enum. The serializer was corrected; retry will use the same frozen experiment.
