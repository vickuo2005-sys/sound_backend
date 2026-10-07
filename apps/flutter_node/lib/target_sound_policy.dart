/// Existing operational alert/event policy, shared without changing thresholds.
bool isOperationalTargetLabel(String label) =>
    label == 'aircraft' || label == 'drone';
