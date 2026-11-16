from contextlib import contextmanager
from collections.abc import Generator, Iterator
import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def configure_observability() -> None:
    resource = Resource.create({
        "service.name": "orchestrator-mock",
        "service.version": "0.1.0",
    })

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint="http://localhost:4317",
                insecure=True,
            )
        )
    )

    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app)


tracer = trace.get_tracer("orchestrator")


@contextmanager
def span(name: str, **attributes: str | int | float | bool) -> Generator:
    with tracer.start_as_current_span(name) as current_span:
        for key, value in attributes.items():
            current_span.set_attribute(key, value)

        try:
            yield current_span
        except Exception as error:
            current_span.record_exception(error)
            current_span.set_status(
                trace.StatusCode.ERROR,
                str(error),
            )
            raise