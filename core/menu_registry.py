# 菜单注册中心:作为插件自描述菜单的聚合器,替代原来从 config.json 读取菜单结构的方式。
# 插件在模块顶层通过 menu_registry.register(...) 声明菜单元数据,框架聚合为三级树(分类/子分类/菜单项)。

from collections import OrderedDict
from typing import Any, Dict, List, Optional


class MenuRegistry:
    """菜单注册中心,聚合插件自描述的三级菜单树。"""

    def __init__(self):
        # 三级树:_categories -> subcategories -> items
        # 每个分类含 title/trigger/description/enabled + subcategories(OrderedDict) + items(OrderedDict)
        # 每个子分类含 title/trigger/description/enabled + items(OrderedDict)
        # 每个菜单项含 text/description/enabled
        self._categories: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def register(self, category: str, item_name: str, text: str = "",
                 subcategory: str = None, description: str = None,
                 category_title: str = None, category_trigger: str = None, category_description: str = None,
                 subcategory_title: str = None, subcategory_trigger: str = None, subcategory_description: str = None) -> None:
        """注册一个菜单项。幂等:重复注册同一项则更新 text/description,不重复插入。"""
        # 创建一级分类(若不存在)
        if category not in self._categories:
            self._categories[category] = {
                "title": category_title if category_title is not None else category,
                "trigger": category_trigger if category_trigger is not None else category,
                "description": category_description if category_description is not None else "",
                "enabled": True,
                "subcategories": OrderedDict(),
                "items": OrderedDict(),
            }

        cat = self._categories[category]

        # 定位目标:子分类或一级分类
        if subcategory is not None:
            if subcategory not in cat["subcategories"]:
                cat["subcategories"][subcategory] = {
                    "title": subcategory_title if subcategory_title is not None else subcategory,
                    "trigger": subcategory_trigger if subcategory_trigger is not None else subcategory,
                    "description": subcategory_description if subcategory_description is not None else "",
                    "enabled": True,
                    "items": OrderedDict(),
                }
            target = cat["subcategories"][subcategory]
        else:
            target = cat

        # 注册菜单项(幂等:重复注册则覆盖文本)
        items = target["items"]
        if item_name not in items:
            items[item_name] = {
                "text": text if text else item_name,
                "description": description if description is not None else "",
                "enabled": True,
            }
        else:
            # 始终更新 text(若 text 非空),更新 description(若非 None)
            if text:
                items[item_name]["text"] = text
            if description is not None:
                items[item_name]["description"] = description

    def get_menu_tree(self) -> Dict[str, Any]:
        """返回完整树 dict,结构兼容原 config.json 的 menu.categories。"""
        tree: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        for cat_name, cat in self._categories.items():
            tree[cat_name] = {
                "title": cat["title"],
                "trigger": cat["trigger"],
                "description": cat["description"],
                "enabled": cat["enabled"],
                "subcategories": OrderedDict(),
                "items": OrderedDict(),
            }
            for sub_name, sub in cat["subcategories"].items():
                tree[cat_name]["subcategories"][sub_name] = {
                    "title": sub["title"],
                    "trigger": sub["trigger"],
                    "description": sub["description"],
                    "enabled": sub["enabled"],
                    "items": OrderedDict(
                        (item_name, {
                            "text": item["text"],
                            "description": item["description"],
                            "enabled": item["enabled"],
                        }) for item_name, item in sub["items"].items()
                    ),
                }
            for item_name, item in cat["items"].items():
                tree[cat_name]["items"][item_name] = {
                    "text": item["text"],
                    "description": item["description"],
                    "enabled": item["enabled"],
                }
        return tree

    def get_main_menu_text(self, global_title=None, global_desc=None) -> str:
        """渲染主菜单文本,格式与原 config_manager.get_main_menu_text() 一致。"""
        title = global_title if global_title is not None else "📋 菜单"

        lines = [title]

        description = global_desc if global_desc is not None else ""
        if description:
            lines.append(f"\n{description}")

        lines.append("")

        for cat_name, cat in self._categories.items():
            if not cat["enabled"]:
                continue
            cat_title = cat["title"]
            cat_desc = cat["description"]
            if cat_desc:
                lines.append(f"📌 {cat_title}")
                lines.append(f"   {cat_desc}")
            else:
                lines.append(f"📌 {cat_title}")

        return "\n".join(lines)

    def get_category_menu_text(self, category_key: str) -> Optional[str]:
        """渲染分类/子分类文本,格式与原 config_manager.get_category_menu_text() 一致。"""
        # 子分类 key 格式: "parent.sub"
        if "." in category_key:
            parent_name, sub_name = category_key.split(".", 1)
            cat = self._categories.get(parent_name)
            if not cat:
                return None
            sub = cat["subcategories"].get(sub_name)
            if not sub:
                return None
            if not sub["enabled"]:
                return f"{sub['title']} 功能已关闭"
            title = sub["title"]
            desc = sub["description"]
            items = sub["items"]
        else:
            cat = self._categories.get(category_key)
            if not cat:
                return None
            if not cat["enabled"]:
                return f"{cat['title']} 功能已关闭"

            # 一级分类且有子分类时:展示子分类列表
            subcats = cat["subcategories"]
            if subcats:
                title = cat["title"]
                desc = cat["description"]
                lines = [title]
                if desc:
                    lines.append(f"📝 {desc}")
                lines.append("")
                for sub_name, sub in subcats.items():
                    if not sub["enabled"]:
                        continue
                    sub_title = sub["title"]
                    sub_desc = sub["description"]
                    lines.append(f"📌 {sub_title}")
                    if sub_desc:
                        lines.append(f"   {sub_desc}")
                return "\n".join(lines)

            # 一级分类无子分类时:展示 items 列表
            title = cat["title"]
            desc = cat["description"]
            items = cat["items"]

        # 渲染 items 列表(一级分类无子分类 或 子分类共用)
        lines = [title]
        if desc:
            lines.append(f"📝 {desc}")
        lines.append("")
        for item_name, item in items.items():
            if item["enabled"]:
                text = item.get("text", item_name)
                lines.append(f"  {text}")
        return "\n".join(lines)

    def get_menu_triggers(self) -> List[str]:
        """返回所有 enabled 的分类与子分类的触发词列表。"""
        triggers = []
        for cat_name, cat in self._categories.items():
            if cat["enabled"]:
                trigger = cat["trigger"]
                if trigger:
                    triggers.append(trigger)
            for sub_name, sub in cat["subcategories"].items():
                if sub["enabled"]:
                    sub_trigger = sub["trigger"]
                    if sub_trigger:
                        triggers.append(sub_trigger)
        return triggers

    def get_category_by_trigger(self, trigger: str) -> Optional[str]:
        """根据触发词查找分类 key。
        
        返回值:
            "__main__" — 匹配主菜单触发词(需由调用方传入 main_trigger 判断)
            "分类名" — 匹配一级分类
            "分类名.子分类名" — 匹配二级子分类
            None — 未匹配
        """
        for cat_name, cat in self._categories.items():
            if cat["trigger"] == trigger:
                return cat_name
            for sub_name, sub in cat["subcategories"].items():
                if sub["trigger"] == trigger:
                    return f"{cat_name}.{sub_name}"
        return None


# 单例导出
menu_registry = MenuRegistry()
