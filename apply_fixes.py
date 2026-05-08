with open('scripts/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. search_goods error handling
content = content.replace(
    '    except Exception as e:\n        print(f"搜索失败:{e}")\n        return []\n\n\nasync def get_goods_detail',
    '    except (aiohttp.ClientError, asyncio.TimeoutError) as e:\n        print(f"搜索失败（网络错误）：{e}")\n        return []\n    except Exception as e:\n        print(f"搜索失败（未知错误）：{type(e).__name__}: {e}")\n        return []\n\n\nasync def get_goods_detail'
)

# 2. get_goods_detail error handling
content = content.replace(
    '    except Exception as e:\n        print(f"获取商品详情失败:{e}")\n        return None\n\n\nasync def compare_goods',
    '    except (aiohttp.ClientError, asyncio.TimeoutError) as e:\n        print(f"获取商品详情失败（网络错误）：{e}")\n        return None\n    except Exception as e:\n        print(f"获取商品详情失败（未知错误）：{type(e).__name__}: {e}")\n        return None\n\n\nasync def compare_goods'
)

# 3. compare_goods error handling
content = content.replace(
    '            except Exception as e:\n                print(f"  ❌ {source_name} 查询失败")',
    '            except (aiohttp.ClientError, asyncio.TimeoutError):\n                print(f"  ❌ {source_name} 查询失败（网络错误）")\n            except Exception as e:\n                print(f"  ❌ {source_name} 查询失败（{type(e).__name__}: {e}）")'
)

# 4. search_and_monitor async input fix (first one)
content = content.replace(
    '    choice = input("\\n请选择 (a/s/n): ").strip().lower()',
    '    loop = asyncio.get_event_loop()\n    choice = await loop.run_in_executor(None, lambda: input("\\n请选择 (a/s/n): "))\n    choice = choice.strip().lower()'
)

# 5. search_and_monitor async input fix (second one)
content = content.replace(
    '            indices = input("> ").strip()',
    '            loop = asyncio.get_event_loop()\n            indices = await loop.run_in_executor(None, lambda: input("> "))\n            indices = indices.strip()'
)

# 6. search_and_monitor error handling improvement
content = content.replace(
    '        except Exception as e:\n            print(f"输入错误:{e}")\n            return\n',
    '        except (ValueError, IndexError) as e:\n            print(f"输入错误：{e}")\n            return\n        except Exception as e:\n            print(f"未知错误：{type(e).__name__}: {e}")\n            return\n'
)

# 7. aiohttp timeout
content = content.replace(
    '    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)\n    try:\n        async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as SESSION:',
    '    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)\n    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15, sock_connect=5)\n    try:\n        async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as SESSION:'
)

with open('scripts/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done!')
