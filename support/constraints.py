"""可解释服务约束: 每条约束对一次重演结果给出"是否满足"与依据。

依据(evidence)是人可读的观测值与阈值对照, 便于主管判断约束为何通过或失败,
而不是只看到一个低预测误差就推断排班合理。
"""

from .simulation import _percentile


class Constraint:
    name = "constraint"

    def check(self, sim: dict) -> dict:  # pragma: no cover - 抽象接口
        raise NotImplementedError

    @staticmethod
    def _result(name: str, satisfied: bool, observed: float, threshold: float, evidence: str) -> dict:
        return {
            "name": name,
            "satisfied": satisfied,
            "observed": observed,
            "threshold": threshold,
            "evidence": evidence,
        }


class MaxWait(Constraint):
    """某渠道已服务工单的等待分位数上限(秒)。"""

    def __init__(self, channel: str, percentile: int, seconds: float) -> None:
        self.channel = channel
        self.percentile = percentile
        self.seconds = float(seconds)
        self.name = f"{channel} 等待 p{percentile} ≤ {seconds:g}s"

    def check(self, sim: dict) -> dict:
        waits = [
            r["wait_hours"] * 3600
            for r in sim["tickets"]
            if r["channel"] == self.channel and r["status"] == "served"
        ]
        observed = _percentile(waits, self.percentile)
        evidence = (
            f"{self.channel} 已服务 {len(waits)} 单, 等待 p{self.percentile} = "
            f"{observed:.0f}s, 阈值 {self.seconds:g}s"
        )
        return self._result(self.name, observed <= self.seconds, observed, self.seconds, evidence)


class MaxAbandonRate(Constraint):
    """某渠道放弃率上限(放弃数 / 到达数)。"""

    def __init__(self, channel: str, rate: float) -> None:
        self.channel = channel
        self.rate = float(rate)
        self.name = f"{channel} 放弃率 ≤ {rate:.0%}"

    def check(self, sim: dict) -> dict:
        own = [r for r in sim["tickets"] if r["channel"] == self.channel]
        arrived = len(own)
        abandoned = sum(1 for r in own if r["status"] == "abandoned")
        observed = abandoned / arrived if arrived else 0.0
        evidence = f"{self.channel} 到达 {arrived} 单, 放弃 {abandoned} 单, 放弃率 {observed:.1%}, 阈值 {self.rate:.0%}"
        return self._result(self.name, observed <= self.rate, observed, self.rate, evidence)


class MaxBacklog(Constraint):
    """某渠道在指定班次边界(缺省为重演截止时刻)的积压上限。"""

    def __init__(self, channel: str, count: int, at_hour: float | None = None) -> None:
        self.channel = channel
        self.count = int(count)
        self.at_hour = at_hour
        where = "重演结束" if at_hour is None else f"小时 {at_hour:g}"
        self.name = f"{channel} 在{where}积压 ≤ {count}"

    def check(self, sim: dict) -> dict:
        hour = sim["horizon_end"] if self.at_hour is None else float(self.at_hour)
        snapshots = [s for s in sim["backlog_snapshots"] if abs(s["hour"] - hour) < 1e-9]
        observed = snapshots[-1]["by_channel"].get(self.channel, 0) if snapshots else 0
        evidence = (
            f"{self.channel} 在小时 {hour:g} 的跨班积压 = {observed} 单, 阈值 {self.count} 单"
        )
        return self._result(self.name, observed <= self.count, observed, self.count, evidence)


class MaxOvertime(Constraint):
    """全员加班总小时上限(交班时仍在处理的工单会处理完再走)。"""

    def __init__(self, hours: float) -> None:
        self.hours = float(hours)
        self.name = f"总加班 ≤ {hours:g}h"

    def check(self, sim: dict) -> dict:
        observed = sum(a["overtime_hours"] for a in sim["agents"].values())
        evidence = f"全员加班合计 {observed:.2f}h, 阈值 {self.hours:g}h"
        return self._result(self.name, observed <= self.hours, observed, self.hours, evidence)
