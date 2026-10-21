"""用户自定义签名插件 — 把逆向出来的签名算法填到这里。

用法示例:
    from shortdrama.core.signature import register, BaseSigner

    class HongguoSigner(BaseSigner):
        name = 'hongguo'

        def sign(self, method, url, params, headers):
            # 这里写逆向出来的算法,比如 X-Bogus
            ts = int(time.time() * 1000)
            bogus = self._xor_bogus(url, params, headers.get('User-Agent', ''), ts)
            return {'X-Bogus': bogus, 'X-Livetime': str(ts)}

    register(HongguoSigner())

然后在 platforms/xxx.py 里:
    headers = {**self._sign_headers(...)}   # 先调签名器生成 header
    headers.update(get_signer('hongguo').sign(...))  # 再叠自定义签名
"""
from shortdrama.core.signature import register
from shortdrama.core.signature import SimpleMd5Signer, HmacSha256Signer

# ====== 注册示例 ======
# 把 secret 换成你抓包拿到的
register(SimpleMd5Signer(secret="your-secret-here"))
register(HmacSha256Signer(secret="your-other-secret"))


# ====== 真实平台签名(等你逆向出来再打开) ======
# register(HongguoSigner())    # 红果 X-Bogus / a-bogus
# register(HemaSigner())       # 河马 sign 算法