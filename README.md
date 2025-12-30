# LiveShell_LocalMode_Pro

## はじめに

2025.11.23(日) 電通大の調布祭のジャンク市にてCerevo LiveShell Proを捕獲するも、既に2025年5月末で【サ終】(サポート終了)となっていた。
しかも、Dashboardも廃止になり、デバイスは正常でも使えない文鎮状態になる。
唯一残されたローカルモード設定もDashboardで行う必要がある(正確に言うと、ローカルモード設定を行う音声ファイルのダウンロードができない)ため、文鎮確定(オブジェ)になる。

https://x.com/Zakkiea/status/1992542645265297659

https://s.cerevo.com/closed.html

<img width="2556" height="1956" alt="スクリーンショット 2025-12-30 14 56 28" src="https://github.com/user-attachments/assets/30a51633-b2db-4a88-acde-b43a3c6fc6b5" />

## Dashboard自作へのトライ

かつて復活させたスマートマットライトの方法(DNSによる名前解決変更、mitmproxyによる解析)でDashboardを自作してLiveShell Proを復活させようと試みましたが、敢えなく撃沈しました。

https://qiita.com/kitazaki/items/37cc80ddca2ca43c3c04

### DNSによる名前解決変更

デバイスの有線ネットワークの設定を固定IPアドレスに変更するとDNSサーバを手動で変更できるため、mitmproxyをインストールしたサーバ(Raspberry Pi)へ設定します。
/etc/hostsファイルに設定

```text:/etc/hosts
192.168.3.12	shell.cerevo.com
```

```bash
$ sudo mitmproxy --mode dns --set dns_use_hosts_file=true
```

#### デバイスがTLS1.0/1.1しかサポートしていない

別のサーバでmitmproxyをReverse Proxyモードで起動します。

```bash
$ mitmproxy --mode reverse:http://shell.cerevo.com@80 --mode reverse:https://shell.cerevo.com@443
```

デフォルトではmitmproxyがTLS1.2以上しか受け付けない設定になっているため、デバイスがTLSハンドシェイクに失敗しました。

<img width="2826" height="90" alt="1" src="https://github.com/user-attachments/assets/5ecf030e-0972-4676-8d02-ca702075a557" />

mitmproxyの起動オプションを変更してTLSのバージョンを下げて解決しました。

```bash
$ mitmproxy --set tls_version_client_min=TLS1 --mode reverse:http://shell.cerevo.com@80 --mode reverse:https://shell.cerevo.com@443
```

### 理由: 「mitmproxyのCA証明書を無視」または「証明書ピンニング(cerevo.com)」

デバイスがmitmproxyのCA証明書を知らない認証局として拒否しているログです。デバイスにmitmproxyのCA証明書をインストールする手段がないためNGです。

![2](https://github.com/user-attachments/assets/5391f994-a0b8-4721-8560-f87b7ec7d1c2)


## ローカルモード設定用音声ファイルの作成

海外のサイトでUltra DashboardというLiveShell Dashboard互換のサイトを見つけました。
ただし、2時間の無料トライアルでもWhatsAppで連絡を取る必要があり、継続利用は有料なので選択肢を諦めました。

https://ultra.starvideo.in/

### 英語のマニュアルで代替えサイトの存在に気づく

まだサポートを継続しているLiveShell Xの英語マニュアルを読んでいたところ、Dashboardではない代替えサイトでローカルモード設定を行うページを見つけました。

https://liveshell-manual.cerevo.com/en/liveshell-x/x-2-4/

<img width="1440" height="878" alt="スクリーンショット 2025-12-30 15 44 40" src="https://github.com/user-attachments/assets/9b4e8826-036d-4042-98e8-80be9011e1ac" />

https://ls-local.cerevo.com/

マニュアルの画面キャプチャ(スクリーンショット)にはLliveShell ProとLiveShell 2のデバイスも選択肢として表示されていたので、一気に期待値が上昇しましたが、残念ながら現在(2025.12.29時点)ではLiveShell Xのみになっていました。

<img width="2942" height="1706" alt="スクリーンショット 2025-12-30 15 51 30" src="https://github.com/user-attachments/assets/f9be95b3-b1bb-4f41-9033-b86d5cac85b6" />

### インターネットアーカイブサイトで過去のサイトコンテンツを発掘

かつて利用したインターネットアーカイブサイトで過去のサイト情報を調査して【サ終】前のコンテンツを入手できました。

https://qiita.com/kitazaki/items/256875ea46fcb3dc2307

【サ終】前(2025.4.8時点)のコンテンツが残されていました。

https://web.archive.org/web/20250408014553/https://ls-local.cerevo.com/

<img width="2944" height="1686" alt="スクリーンショット 2025-12-30 15 51 59" src="https://github.com/user-attachments/assets/7babbac4-1f13-45ff-b21a-8377da5931ae" />

### 音声ファイルのダウンロード

<img width="2882" height="1314" alt="スクリーンショット 2025-12-30 16 15 25" src="https://github.com/user-attachments/assets/3efec45f-401d-4457-a07f-bfcc6d83464f" />


### デバイスのローカルモード設定

最初にデバイスをオフラインモードに設定変更する必要があります。

![offline](https://github.com/user-attachments/assets/7410d4f9-5ac9-4f4c-986a-7b1b197c636a)


ダウンロードした音声ファイルを再生して、パソコン(ヘッドフォン端子)からデバイス(マイク入力端子)へ音声を流し込みます。
成功すると画面が切り替わります。

#### RTSPモード

デバイスはクライアントからの接続待ち状態になります。
URLはrtsp://192.168.3.16/liveの形式(デバイスのディスプレイに表示)になり、VLC Playerで動作確認しました。

![RTSP](https://github.com/user-attachments/assets/9fe4f1e9-b827-4c85-a793-e698f6bdb45a)


![IMG_0951](https://github.com/user-attachments/assets/e8209475-b68c-4add-9dad-151dd59f0536)

#### RTMPモード

デバイスはRTMP配信状態になります。
YouTubeLiveで動作確認しました。

![RTMP](https://github.com/user-attachments/assets/ac4a8951-5c2f-4ef6-8a0d-ef311b6e1fdc)


![YouTubeLive](https://github.com/user-attachments/assets/145e1c08-3b4c-4e8b-9ec1-c432e3a531c6)



## さいごに

コンテンツの実装都合でトップページに配置する必要がありますが、文鎮確定のデバイスを復活させることができました。

テストサイトです。

https://kitazaki2.cloudfree.jp/

