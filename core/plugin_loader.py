import os
import sys
import importlib
import inspect
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger("plugin_loader")

# 项目根目录(plugin_loader.py 位于 core/ 下,上溯一层即项目根)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 已加载插件注册表:模块名 -> 模块对象
_loaded_plugins: Dict[str, object] = {}


def load_plugins(path: str) -> List[str]:
    """加载指定目录下的所有 Python 模块作为插件。
    
    Args:
        path: 插件目录路径(相对路径,如 "plugins")
    
    Returns:
        成功加载的模块名列表
    """
    loaded = []
    if not os.path.isdir(path):
        return loaded
    
    # 相对路径基于项目根目录解析,确保跨目录运行
    if not os.path.isabs(path):
        abs_path = os.path.join(_PROJECT_ROOT, path)
    else:
        abs_path = path

    logger.info(f"Loading plugins from {abs_path}")

    for filename in os.listdir(abs_path):
        if not filename.endswith('.py') or filename.startswith('_'):
            continue
        
        module_name = filename[:-3]  # 去掉 .py
        
        # 跳过已加载的
        if module_name in _loaded_plugins:
            continue
        
        try:
            # 将插件目录加入 sys.path 以支持 from plugins.xxx import yyy
            if abs_path not in sys.path:
                sys.path.insert(0, os.path.dirname(abs_path))
            
            # 以 plugins.module_name 形式导入
            full_name = f"{path}.{module_name}" if not path.endswith('/') else f"{path.rstrip('/')}.{module_name}"
            # 标准化路径为模块路径
            pkg_name = path.replace('/', '.').replace('\\', '.')
            full_name = f"{pkg_name}.{module_name}"
            
            module = importlib.import_module(full_name)
            _loaded_plugins[module_name] = module
            logger.info(f"Loaded plugin: {module_name}")
            loaded.append(module_name)
        except Exception as e:
            logger.error(f"Failed to load plugin '{module_name}': {e}")
            import traceback
            logger.error(f"Plugin '{module_name}' load traceback:", exc_info=True)
    
    return loaded


def load_plugin(module_name: str) -> bool:
    """加载单个插件。
    
    Args:
        module_name: 插件模块名(不含路径前缀,如 "group_admin")
    
    Returns:
        是否加载成功
    """
    if module_name in _loaded_plugins:
        return True
    
    try:
        full_name = f"plugins.{module_name}"
        module = importlib.import_module(full_name)
        _loaded_plugins[module_name] = module
        return True
    except Exception as e:
        logger.error(f"Failed to load plugin '{module_name}': {e}")
        import traceback
        logger.error(f"Plugin '{module_name}' load traceback:", exc_info=True)
        return False


def reload_plugin(module_name: str) -> bool:
    """热重载插件:卸载后重新导入。
    
    Args:
        module_name: 插件模块名(如 "group_admin")
    
    Returns:
        是否重载成功
    """
    full_name = f"plugins.{module_name}"
    
    # 从注册表中移除
    _loaded_plugins.pop(module_name, None)
    
    # 从 sys.modules 中移除(包括所有子模块)
    keys_to_remove = [k for k in sys.modules if k == full_name or k.startswith(full_name + '.')]
    for key in keys_to_remove:
        del sys.modules[key]
    
    # 重新加载
    try:
        module = importlib.import_module(full_name)
        _loaded_plugins[module_name] = module
        return True
    except Exception as e:
        logger.error(f"Failed to reload plugin '{module_name}': {e}")
        import traceback
        logger.error(f"Plugin '{module_name}' reload traceback:", exc_info=True)
        return False


def get_loaded_plugins() -> Dict[str, object]:
    """获取已加载插件字典"""
    return _loaded_plugins


def get_plugin(name: str):
    """获取指定插件模块"""
    return _loaded_plugins.get(name)
