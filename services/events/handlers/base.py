from services.events.envelope import thaw


class DomainHandler:
    """Explicit adapter. Observation has no path to the injected mutating callable.

    execute_for_test is never wired into FastAPI/bus subscribers. The name emphasizes
    that durable replay safety is not established for these existing domain functions.
    """
    input_type = None
    output_type = None

    def __init__(self, domain_call=None):
        self.domain_call = domain_call

    def _check(self, event):
        if event.event_type != self.input_type:
            raise ValueError('Unexpected handler event type')

    def observe(self, event, canonical_result):
        self._check(event)
        return event.transition(self.output_type, canonical_result)

    def execute_for_test(self, event):
        self._check(event)
        if self.domain_call is None:
            raise RuntimeError('Explicit existing domain function required')
        return self.observe(event, self.call_domain(event))

    def call_domain(self, event):
        return self.domain_call(thaw(event.payload))
