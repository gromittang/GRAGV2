# MySQL系统表

## Schema来源

从 `tfrmdataobj` 和 `tfrmdataprop` 表读取元数据。

## tfrmdataobj (表信息)

| 字段 | 说明 | 别名 |
|------|------|------|
| DataObjCode | 表代码 | table_name |
| DataObjName | 表名称 | display_name |
| ObjDesc | 表描述 | description |
| DataObjType | 对象类型 | '0'=表 |

## tfrmdataprop (字段信息)

| 字段 | 说明 | 别名 |
|------|------|------|
| FieldName | 字段名 | column_name |
| FieldDesc | 字段描述 | display_name |
| DataType | 数据类型代码 | data_type |
| DataWidth | 数据长度 | data_length |
| DataDec | 数据精度 | description |
| DataObjCode | 所属表 | table_name |
| FieldIndex | 字段顺序 | position |

## DataType代码映射

| 代码 | 类型 |
|------|------|
| 0 | INTEGER |
| 1 | VARCHAR |
| 2 | DATETIME |
| 3 | DECIMAL |
| 4 | TEXT |
| 5 | DATE |
| 6 | TIME |
| 7 | BOOLEAN |
| 8 | BLOB |

## 连接配置

| 参数 | 默认值 |
|------|------|
| host | 配置文件 |
| port | 3306 |
| database | unwms |
| minsize | 1 |
| maxsize | 5 |