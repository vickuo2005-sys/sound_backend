import pytest
from tools.benchmark_event_bus import run


@pytest.mark.parametrize('nodes',[4,20,50,100])
def test_architecture_bursts_bounded_and_ordered(nodes):
    result=run(nodes)
    assert result['bus']['consumed']==nodes*20
    assert result['ordering_violations']==0
    assert result['bus']['queue_depth']==0
    assert result['python_allocations_peak_bytes']>0
