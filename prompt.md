我的aivudaOS是一个自制的小型的用于安装和运行我自己的aivudaAppStore里的应用的OS，目前安装包里具体的结构还待定可以修改。我需要你帮我重构aivudaOS，按照OS的职能划分为core（核心服务层（纯逻辑，不涉及 HTTP））、gateway/（唯一 server，fastapi， 没有 业务逻辑，用来调用core里各种的service提供REST接口，）、ui（OS的ui，基于Vue和vite），apps（应用安装目录，每个app完全独立，可以安装多个版本、但实际用的只能是一个指定的版本）、config（OS的全局配置文件、apps的配置文件，全局配置与 app 配置分离）、data(运行时数据（不可放在 app 目录内）)，这样设计怎么样，还缺什么不



针对我这个aivudaOS，开发app安装和运行core service，用来安装、运行、管理app。先用本地上传app安装包，然后安装app到各个对应位置，config放到config目录里对应位置，核心程序放到apps里对应版本位置，同时有记录app信息的数据库，之后再设计app的启动、停止、升级、自启动对应的服务，并添加到gateway里的rest api。原有的app体系全部可以覆盖。
