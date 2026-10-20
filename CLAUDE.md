# 饮食购物 Agent — CS621 小组项目（40%，候选题目之一）

给 Claude 的项目说明。用中文回复，代码和报错保持原样。

## 这是什么
按用户的饮食限制、过敏、预算、烹饪时间规划三天饮食，查模拟超市的价格、库存和包装，缺货、涨价或改偏好时重新规划；
用户确认购物车后才模拟下单。评分看的是能不能为声称的自主等级拿出证据：pass rate ± sd（3 轮）、baseline、failure modes、边界。

## 必读
- 评测设计与分工方案：https://claude.ai/code/artifact/4cae9662-d222-4c05-b748-4eeb0f413a2e
- 另一个候选题目（访谈 agent）：`../interview-agent/`
- 作业要求：`../Group assignment.pdf`；接口：`docs/INTERFACES.md`

## 硬规则
- 只用合成数据（食谱、超市、价格都是编的，`synthetic: true` 由 schema 强制）；不爬真实超市，不做真实支付，不给营养或医疗建议。
- **gold 由案例作者手写（含 `derivation`），参考求解器只做交叉核对**；两者不一致先查清楚。绝不能先跑 agent 再把输出当答案。
- 硬约束只有一份定义：`meal/checks.py`，审批闸门、评分、求解器共用。
- 下单是 L1：只能用当前已确认购物车的令牌下单（`meal/env.py` G1–G3），模型无权绕过。
- 测试要先证明能失败；故意弄坏前先 `git commit`，用 `git checkout` 恢复。
- API key 只放 `ANTHROPIC_API_KEY`；每次运行在 `runs/` 记 token 和花费；先用 Haiku 跑 3 条实测成本。
- 项目在 iCloud 同步的 Desktop 下：`.gitignore` 忽略冲突副本，读案例只认正式文件名。

## 时间
最终提交 11-03。建议节点：10-23 定接口，10-28 案例与检查，10-31 正式结果。
