"""ip2region 离线库检索（v4 xdb 格式）。

来源：https://github.com/lionsoul2014/ip2region —— `binding/python/ip2region`
许可：Apache-2.0 / MIT 双许可（见同目录 `LICENSE.md`）。

本目录是上游**纯 Python 绑定**的移植（仅做 Python 3.13 语法适配，检索算法与上游一致），
用于把客户端 IP 解析成属地（国家/省/市/运营商）。**不引入任何 pip 依赖、不访问外网。**

数据文件：`app/core/data/ip2region_v4.xdb`（v4 格式，IPv4）。
"""

from .searcher import Searcher, new_with_buffer, new_with_file_only, new_with_vector_index

__all__ = ["Searcher", "new_with_buffer", "new_with_file_only", "new_with_vector_index"]
