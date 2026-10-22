# 关联关系比对方法

## 比较优先级

`taxNo` > `bankAccount` > `contactPhone` > `contactName` > 名称高度相似（包含关系或去掉公司后缀后相同）。

名称相似不能单独定为高风险。

## 大额与交叉接单

- 大额：关联主体 PO `totalWithTax` 合计 >= 100,000 元
- 交叉接单：相近时间窗口内相同 `itemCode`，或同一项目描述
- 高风险：共享税号/账号/电话，并且（大额或交叉接单或已实际付款），且无申报
- 中风险：仅电话/联系人/简称重复，金额较小或可解释为重复建档
- 低风险：标识符无交叉

## 沙箱分组示例

```python
groups = defaultdict(list)
for v in records:
    key = v.get("taxNo")
    if key:
        groups[key].append(v.get("id"))
result = {k: ids for k, ids in groups.items() if len(ids) > 1}
```

沙箱已注入 `defaultdict`、`Counter`、`to_number`。不要写 `import`。

## 表述

查询结果为空写成「ERP 中未检索到关联交易申报」，不要写成「肯定不存在申报」。  
申报完成不自动消解，仍须评估交叉接单与定价公允性。  
若共享银行账号且已实际付款，即使申报缺失也可按高风险确认。