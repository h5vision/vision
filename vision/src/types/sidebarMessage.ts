export enum SidebarCommand {

    CheckBackend = "checkBackend",

    GetModelsInfo = "getModelsInfo",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    OpenDBExternal = "openDBExternal",

    GetProjectInfo = "getProjectInfo",

    GetProjectGitInfo = "getProjectGitInfo",

    GetGuideStatus = "getGuideStatus",

    GetProjectList = "getProjectList",

    GenerateBriefByCopilot = "generateBriefByCopilot",

    GetProjectBrief = "getProjectBrief",

    GenerateRAGTEST = "generateRAGTEST",

    RemoveRAGTEST = "removeRAGTEST",

    UpdateEndpoint = "updateEndpoint",

    UpdateModelId = "updateModelId",

    UpdateCommitId = "updateCommitId",

    SetStreaming = "setStreaming",
    
    GetStreamingStatus = "getStreamingStatus",

    ToggleGuide = "toggleGuide",

    ShowDependencyGraph = "showDependencyGraph",

    InitializeDependencyGraph = "initializeDependencyGraph"
}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}