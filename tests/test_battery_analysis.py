import numpy as np
from gb_platform_v2.battery_analysis import schedule

def test_battery_feasible_and_no_simultaneous_flow():
    prices=np.r_[np.full(24,5.),np.full(24,120.)]
    c,d=schedule(prices)
    assert np.max(c*d)<1e-6
    assert np.sum(prices*(d-c)*.5)>0
    eta=np.sqrt(.88)
    soc=1+np.cumsum((eta*c-d/eta)*.5)
    assert soc.min()>-1e-5 and soc.max()<2+1e-5
    assert abs(soc[-1]-1)<1e-5
    assert d.sum()*.5<=2+1e-5
