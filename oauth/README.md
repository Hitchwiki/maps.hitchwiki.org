TODO: try

Option B: Use Cloudflare’s “Rules → Configuration Rules” (new method, 2024–2025)

Go to Rules → Configuration Rules in your dashboard.

Click Create Rule.

Give it a name like “Bypass OAuth endpoint”.

For Expression, use something like:

(http.request.uri.path contains "/w/index.php" and http.request.uri.query contains "title=Special:OAuth")


Under Settings, choose:

Security Level → Essentially Off

Cache Level → Bypass

Disable Browser Integrity Check (optional)

Save and deploy. This will make Cloudflare act as a “dumb proxy” for that endpoint — requests will pass straight through.

----

testing oauth from nomadwiki here

run the example app

```
pip install flask requests requests-oauthlib
python3 app.py
```

`http://127.0.0.1:5000/login` should not throw errors. right now it gives: 404/500/TokenRequestDenied

Currently it gives
```
 * Serving Flask app 'app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.211.61.9:5000
Press CTRL+C to quit
127.0.0.1 - - [28/Sep/2025 11:12:52] "GET / HTTP/1.1" 404 -
127.0.0.1 - - [28/Sep/2025 11:12:53] "GET /favicon.ico HTTP/1.1" 404 -
127.0.0.1 - - [28/Sep/2025 11:12:54] "GET /sw.js HTTP/1.1" 404 -
[2025-09-28 11:12:59,106] ERROR in app: Exception on /login [GET]
Traceback (most recent call last):
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/flask/app.py", line 1473, in wsgi_app
    response = self.full_dispatch_request()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/flask/app.py", line 882, in full_dispatch_request
    rv = self.handle_user_exception(e)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/flask/app.py", line 880, in full_dispatch_request
    rv = self.dispatch_request()
         ^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/flask/app.py", line 865, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/oauth/app.py", line 23, in login
    request_token = oauth.fetch_request_token(REQUEST_TOKEN_URL)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/requests_oauthlib/oauth1_session.py", line 282, in fetch_request_token
    token = self._fetch_token(url, **request_kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/till/projects/hitchhiking/hitch/.venv/lib/python3.12/site-packages/requests_oauthlib/oauth1_session.py", line 364, in _fetch_token
    raise TokenRequestDenied(error % (r.status_code, r.text), r)
requests_oauthlib.oauth1_session.TokenRequestDenied: Token request failed with code 403, response was '<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><meta http-equiv="X-UA-Compatible" content="IE=Edge"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box;margin:0;padding:0}html{line-height:1.15;-webkit-text-size-adjust:100%;color:#313131;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif,"Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol","Noto Color Emoji"}body{display:flex;flex-direction:column;height:100vh;min-height:100vh}.main-content{margin:8rem auto;padding-left:1.5rem;max-width:60rem}@media (width <= 720px){.main-content{margin-top:4rem}}.h2{line-height:2.25rem;font-size:1.5rem;font-weight:500}@media (width <= 720px){.h2{line-height:1.5rem;font-size:1.25rem}}#challenge-error-text{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgZmlsbD0ibm9uZSI+PHBhdGggZmlsbD0iI0IyMEYwMyIgZD0iTTE2IDNhMTMgMTMgMCAxIDAgMTMgMTNBMTMuMDE1IDEzLjAxNSAwIDAgMCAxNiAzbTAgMjRhMTEgMTEgMCAxIDEgMTEtMTEgMTEuMDEgMTEuMDEgMCAwIDEtMTEgMTEiLz48cGF0aCBmaWxsPSIjQjIwRjAzIiBkPSJNMTcuMDM4IDE4LjYxNUgxNC44N0wxNC41NjMgOS41aDIuNzgzem0tMS4wODQgMS40MjdxLjY2IDAgMS4wNTcuMzg4LjQwNy4zODkuNDA3Ljk5NCAwIC41OTYtLjQwNy45ODQtLjM5Ny4zOS0xLjA1Ny4zODktLjY1IDAtMS4wNTYtLjM4OS0uMzk4LS4zODktLjM5OC0uOTg0IDAtLjU5Ny4zOTgtLjk4NS40MDYtLjM5NyAxLjA1Ni0uMzk3Ii8+PC9zdmc+");background-repeat:no-repeat;background-size:contain;padding-left:34px}@media (prefers-color-scheme: dark){body{background-color:#222;color:#d9d9d9}}</style><meta http-equiv="refresh" content="360"></head><body><div class="main-wrapper" role="main"><div class="main-content"><noscript><div class="h2"><span id="challenge-error-text">Enable JavaScript and cookies to continue</span></div></noscript></div></div><script>(function(){window._cf_chl_opt = {cvId: '3',cZone: 'nomadwiki.org',cType: 'managed',cRay: '98621f494d4abe66',cH: 'vuHfJCUU4fkNL.9yX5HFlPGqA7m78Gctz4DvpPE8s1M-1759050779-1.2.1.1-6gWd0RhvtpTuii_LlHqo.IjWqQbkYzSb7ruATbbxAkGcsa5R2cziG6lhKVg_YcVB',cUPMDTk:"\/w\/index.php?title=Special:OAuth\/initiate&__cf_chl_tk=vKDJiC8n8yygwnwHXpCGn3.KjCODCNVR4KbBowwu2Z8-1759050779-1.0.1.1-dYEZscICz6EzHnymWuQLbu_te4CPik1cXuinL4Y9Ibg",cFPWv: 'b',cITimeS: '1759050779',cTplC:0,cTplV:5,cTplB: 'cf',fa:"\/w\/index.php?title=Special:OAuth\/initiate&__cf_chl_f_tk=vKDJiC8n8yygwnwHXpCGn3.KjCODCNVR4KbBowwu2Z8-1759050779-1.0.1.1-dYEZscICz6EzHnymWuQLbu_te4CPik1cXuinL4Y9Ibg",md: 'f7CxFLZcDTqKrmGvYIfCjSlM4aevcDMzJsoYDRFeIug-1759050779-1.2.1.1-1Y8gc7dOndYAZ89SPFldjASZLFv1vceQzai7Ztk0_D7.go90T6NmQR3pTUm96YLgQgqAalrtdHa_8dYx8w6LrMLR5d1ha0hyAmLrlQg4UVf1GQOlYsGBBg5Sj7q7rI5HVcZO_DH.yhdTBUhbd0MWvChGilsf7SJfUuiTiYrdzPASTXLAZcR85ujo8q_LkYaJTdPZUnXxqWH5O7CxPEqMJReoPNnZPF.fEqwMsbuy2CFHrNXu7X3gQ5lCJtKrxNYDrE762Qy6C5.lXdYCk1ccLsW9G4Eccb8OBsuOqqY.v4rNddpIypPKrKrUCjdbF6YO708gBPfBT6w5iDu.u8dK7Cx.5gRqpXzTEA9EvmZOg8HpMMgMtjN3Wp6Qd_wh84CDuJPUedegoZ7zRTBfpf3rHBpRKIQrk38JbeppMHPkn5WNsFfp3328cQC0_mzTDCKzV47fylZVlqciiuTs_ApjviVBuB_BLq_ykqCcwUkivyuj4xXn40Y28y.6USOLluxBgny0mTrDGdoqCsDJYRsmukquVvDAmWJg3Gcpbn11ADHzDlNLrED09983jfyi_HtxTmAI7uq2QJpuOlOP6x11amYmUdiz2QBX.IkTuOKyRUAWDFEGdNYER5nGgZG5e9aRR8stPaE9.yo3Hg1iISLJhdSDba8OiSbLyekWQxMmTiSSyPD0wlwrIC2jXIzpXpfHACO3T_tJfsppd5mw2DolQJLLy2eA1Y_NIaMmi4d_rKhuS.VfArBKta4hQJinMj1DOGLNdw5rlA6SiUOvHeF6loej1IyQadcxBeMmV7avsdifnl__rMbw5C1_I2NTKJLN.ZljN2_q11RPy1t40ZmeoOQHw3SIKbGslSPYxM_LnAI',mdrd: 'rbZ_s0ghWTWTwYYlUsNK8BWQzj1M.HlzL8GQz8MRdjQ-1759050779-1.2.1.1-94ZYhj8YxYnzVd.D5gfM44sepiLi5XlVWbrjbImZSF0i_RWx7FoYIqhFUEx_O.0lF7qhMc_1BcHI.yytFV5zeRG8UuneMdLhz6CeU6kYqCorkeOiOsL3P6UdZzY0jNS39TnkQhqyfwsK7MEpDlB2GpHmJuggr0OlRPfADiaU9wFyWtzL9mEs_nx5Tfnw9iRRS9BSsxZYcesXn.errrpt_SxwMCrZYYWHGsjK_8ZaNOEcs60slMR0VcXDIZeEZKMhtBirbK1G0ZsaSTd5MmQZqB7ZxPMV6DzPsvIpjIjauiKKgGc7s6l2V22.rHT5CmcwD4gnKJ11wWVpsbuUUM8eI5sbLpInsvNuHUJoEl6sBE3PBKAdd5sef2VJXbsyRdwF.N4JDWipt6sUmawNIfcSKsuVfNKX_HO0Te64upF2oCgzB1qkoo2EvXFcn3NZPtlRJe1pqRjTrx_H.hefNToqeZC.dQtVIi13Z1YRWA37XvQZtWyRtCFjJQo8OXQnhuygA_1VXeCBV.XkSBnn0mhfvCY3mHaNbPAgGarjOGuUEr2wKjJHhgWh9A7cQPeViBpi_dew.Y__zupqyhkpt0VArnoL4pFDQEk2u3ac2ab72floEHJ1sfqJNv949TE79BkIUaB_SD6cDnEKedBA9bjDWi0VBSxz.DAF9_Cne5m3LQVuc03ktwkaRiHXrGyiKRNVW6NyYKQEsSsfGouWJwDazmN03X1_nFZNNQYGQuny2P9LC9pgGegJ5uu4A_.jwn0ttbUgQDyQeg9MwxdbzrGB1tnpEOlJzvs_XgaCxg1lZqp10PiqsE0z8XiQKhRqozRcC8L329Q4p_7jL0RbcfxGk_PTEhUf6kzAG4HAFQBHAx1stsp.y7Vw5bnGXmsNF.1uvlhV6TWwbYi_RiZA7UeqkOnYqIwCpPJ_rYzsJdGi3k8hyZ204ZM_j4LnOrwiiGv_dqau_mCJ86LckFyh6H9r3CiNaO2JbAFoONiRDPj9c_FZJv5_VM.kZIElvSLLAXq.OFzmw.yJI6DXfN0UZTuyHzUrSZybciWlyzpIe9hLc4kmt3IxHX9I2XkoYLL.GMk3aseWwTepoxyYAcYp3Kjdblj_I6Ntn.FOmq.2Qfn.6YwwWgbm63q_nYlhov_OK_CaXrImMoebCSmkYR2jq9ntgVWa8_HcN8IvysxVtgfnsyfBsQM4feFO.rYbVLzPK2xvhuQYAUQ2R6lPvAekS9d_QXVRWBUzda3qOtXQNxZh7sysJkwLJ8QH.UHdJoITXvmojYAGuCX.MTh_zT5GxJHffnk6JCBGhCgIO1I_7KcOdLSg1zzuLY.31xFTCzJRf9doDF3esKz1a_tq09t2sj9i8erbx6yIK6nHYTHAVnZlqXzw.hoaqh6SE5kAusrc8QKuHRsLA8a2VmE1CcKbGBmJ7NPO6wLGZE8v39MXkdyndOnN.fpA9vsNZIQ9D_FlPHhnf4VVnp0hDfUSC2EW6NyTOkrIzuPzlfWLFQF35t2B7QVBwdG4MJnvCFiHTSMjUsmjiIWPQIWGdvDP7AXEhUsr8.IVngS2gyezvu0W_a9ufrULe0nBJZCZM24D4Uzj3N5p.wx5IQKPqk.B1fCWdqB3EsVpXSL5BYwB7srbfTdlSrrZUpCHqj8Z3o3DU1VK9fJF_p2AH4xwblexVyLeVZTwtlCK_kZiBVAfPS64xEZjwpGN72Rk8gKaoehW6zdq2gZ7BjEzFt3kUNmiYabDNb70fx95OBwmuyCAA6_Aqa921KPQokokAyG31YmxwTmRGyHDDRjPgi75rpSHsTpdEMj4ZF84BCFaW5_LGHHJg8H4iCBAtCDY8gSMkYKf02.UuSKiXpqs9UpbqOnSM0wqNG4hv9ZbU8ojEDqkZcYzkNkvFtWlWhcL5Fn62SZy_O83u6rPst4UUMU7Sif7bwMSaJViyMebJ8662h0cpKYU32iZri0vpTZhif30xS6KHpbpwDBWbqqyDLhYBFYVwI2FD1bYFgdeJZq.Q6KovLq9jVzhvpm_ssoWL7vKh.BvyiOCI.XfE78UIjn58CkOXBT8LNyzfhXZb3LXgwrfcmU3ld94ZFPZhx8hIRwJYGzKn14QdtsYGL5tyF570El6pbl_6EhqnyBKzo39f.z4RiIQojI46QJlqXRSE9f98Xi_OzvQTeMf3QdMSeQ.vNhsSU_UbKj6zMcc34CPdqKIyT8OaDx4JEjAid0F7SYVTD4enYLh3um5AglTj0STPoGqMabrLv9K6aAW450IX5cZeKu2P7zcoVpRkIAAYXvqeqXQ1snS19BdVC0oVraH4qElDCYf8IRMqmSRycnas4yCXarD1Ygv8EMIMP46EXzqDlnFcf6udVa6F0VS6kc3KxBdOcvjf7ByPHWgoHoARo6Dhr6pZTv0PfChMPk55cdsfx4nHJunq2k6wD45McgJl6HXBKSfNtrVl2265IYHhEmQUnQDSuX.giuxS_FKqev7eHYcAC6s3zUl7Kkh.eLljDO5wViSRgLfhfv54.xuDfq9Pl_aJ0xj_YHUgfvPsEN7dM.kQTnL6pFe_dTmDaSZJlfCb3SyuHPnCxmqKUMEg1BQzABOdBaP4IU',};var a = document.createElement('script');a.src = '/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1?ray=98621f494d4abe66';window._cf_chl_opt.cOgUHash = location.hash === '' && location.href.indexOf('#') !== -1 ? '#' : location.hash;window._cf_chl_opt.cOgUQuery = location.search === '' && location.href.slice(0, location.href.length - window._cf_chl_opt.cOgUHash.length).indexOf('?') !== -1 ? '?' : location.search;if (window.history && window.history.replaceState) {var ogU = location.pathname + window._cf_chl_opt.cOgUQuery + window._cf_chl_opt.cOgUHash;history.replaceState(null, null,"\/w\/index.php?title=Special:OAuth\/initiate&__cf_chl_rt_tk=vKDJiC8n8yygwnwHXpCGn3.KjCODCNVR4KbBowwu2Z8-1759050779-1.0.1.1-dYEZscICz6EzHnymWuQLbu_te4CPik1cXuinL4Y9Ibg"+ window._cf_chl_opt.cOgUHash);a.onload = function() {history.replaceState(null, null, ogU);}}document.getElementsByTagName('head')[0].appendChild(a);}());</script></body></html>'.
127.0.0.1 - - [28/Sep/2025 11:12:59] "GET /login HTTP/1.1" 500 -
127.0.0.1 - - [28/Sep/2025 11:13:00] "GET /sw.js HTTP/1.1" 404 -
^C%    
```
