/**
 * Project Explorer Dashboard Plugin
 *
 * Displays tracked projects and their file structures.
 * Allows linking sessions to projects.
 */
(function () {
    "use strict";

    const SDK = window.__HERMES_PLUGIN_SDK__;
    const { React } = SDK;
const {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Badge,
  Button,
  Input,
} = SDK.components;
    const { useState, useEffect, useCallback } = SDK.hooks;
    const { cn, timeAgo } = SDK.utils;

    function ProjectsPage() {
        const [view, setView] = useState("projects");
        const [projects, setProjects] = useState([]);
        const [sessions, setSessions] = useState([]);
        const [selectedProject, setSelectedProject] = useState(null);
        const [projectTree, setProjectTree] = useState(null);
        const [loading, setLoading] = useState(true);
        const [treeLoading, setTreeLoading] = useState(false);
        const [searchQuery, setSearchQuery] = useState("");
        const [error, setError] = useState(null);
        
        const [linkDialogOpen, setLinkDialogOpen] = useState(false);
        const [selectedSession, setSelectedSession] = useState(null);
        const [projectPathInput, setProjectPathInput] = useState("");

        // New state for PE-8 components
        const [projectStats, setProjectStats] = useState(null);
        const [statsLoading, setStatsLoading] = useState(false);
        const [kbSearchQuery, setKbSearchQuery] = useState("");
        const [kbSearchResults, setKbSearchResults] = useState([]);
        const [kbSearchLoading, setKbSearchLoading] = useState(false);
        const [kbStatus, setKbStatus] = useState(null);
        const [activityFeed, setActivityFeed] = useState([]);
        const [activityLoading, setActivityLoading] = useState(false);

        // Collapsible tree state
        const [expandedPaths, setExpandedPaths] = useState(new Set());

        const toggleFolder = useCallback(function(path) {
            setExpandedPaths(function(prev) {
                var next = new Set(prev);
                if (next.has(path)) {
                    next.delete(path);
                } else {
                    next.add(path);
                }
                return next;
            });
        }, []);

        var resetExpandedPaths = useCallback(function() {
            setExpandedPaths(new Set());
        }, []);

        const fetchProjects = useCallback(function () {
            setLoading(true);
            setError(null);
            SDK.fetchJSON("/api/plugins/project-explorer/projects")
                .then(function (data) {
                    setProjects(data.projects || []);
                })
                .catch(function (err) {
                    setError("Failed to load projects");
                    console.error(err);
                })
                .finally(function () {
                    setLoading(false);
                });
        }, []);

const fetchSessions = useCallback(function () {
  SDK.fetchJSON("/api/plugins/project-explorer/sessions")
    .then(function (resp) {
      setSessions(resp.sessions || []);
    })
    .catch(function (err) {
      console.error("Failed to load sessions:", err);
    });
}, []);

        const fetchProjectTree = useCallback(function (projectId) {
            setTreeLoading(true);
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/tree?depth=5")
                .then(function (data) {
                    setProjectTree(data.tree);
                })
                .catch(function (err) {
                    console.error("Failed to load tree:", err);
                    setProjectTree(null);
                })
                .finally(function () {
                    setTreeLoading(false);
                });
        }, []);

        // PE-8-1 & PE-8-2: Fetch project stats (LOC and file types)
        const fetchProjectStats = useCallback(function (projectId) {
            setStatsLoading(true);
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/stats")
                .then(function (data) {
                    setProjectStats(data);
                })
                .catch(function (err) {
                    console.error("Failed to load stats:", err);
                    setProjectStats(null);
                })
                .finally(function () {
                    setStatsLoading(false);
                });
        }, []);

        // PE-8-3: Fetch KB status
        const fetchKbStatus = useCallback(function (projectId) {
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/kb/status")
                .then(function (data) {
                    setKbStatus(data);
                })
                .catch(function (err) {
                    console.error("Failed to load KB status:", err);
                    setKbStatus(null);
                });
        }, []);

        // PE-8-3: Search KB
        const searchKb = useCallback(function (projectId, query) {
            if (!query || !query.trim()) {
                setKbSearchResults([]);
                return;
            }
            setKbSearchLoading(true);
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/kb/search?q=" + encodeURIComponent(query))
                .then(function (data) {
                    setKbSearchResults(data.results || []);
                })
                .catch(function (err) {
                    console.error("KB search failed:", err);
                    setKbSearchResults([]);
                })
                .finally(function () {
                    setKbSearchLoading(false);
                });
        }, []);

        // PE-8-4: Fetch activity feed
        const fetchActivityFeed = useCallback(function (projectId) {
            setActivityLoading(true);
            SDK.fetchJSON("/api/plugins/project-explorer/projects/" + projectId + "/activity?limit=20")
                .then(function (data) {
                    setActivityFeed(data.activities || []);
                })
                .catch(function (err) {
                    console.error("Failed to load activity:", err);
                    setActivityFeed([]);
                })
                .finally(function () {
                    setActivityLoading(false);
                });
        }, []);

        useEffect(function () {
            fetchProjects();
            fetchSessions();
        }, [fetchProjects, fetchSessions]);

        useEffect(function () {
            if (selectedProject) {
                fetchProjectTree(selectedProject.id);
                resetExpandedPaths();
                // PE-8: Fetch new data for stats, KB, and activity
                fetchProjectStats(selectedProject.id);
                fetchKbStatus(selectedProject.id);
                fetchActivityFeed(selectedProject.id);
                // Reset search state
                setKbSearchQuery("");
                setKbSearchResults([]);
            } else {
                setProjectTree(null);
                setProjectStats(null);
                setKbSearchResults([]);
                setActivityFeed([]);
            }
        }, [selectedProject, fetchProjectTree, resetExpandedPaths, fetchProjectStats, fetchKbStatus, fetchActivityFeed]);

        var filteredProjects = projects;
        if (searchQuery) {
            var query = searchQuery.toLowerCase();
            filteredProjects = projects.filter(function (p) {
                return p.name.toLowerCase().includes(query) || p.path.toLowerCase().includes(query);
            });
        }

        function handleLinkSession(session) {
            setSelectedSession(session);
            setProjectPathInput(session.project_path || "");
            setLinkDialogOpen(true);
        }

        function submitLinkProject() {
            if (!projectPathInput.trim()) return;
            
            SDK.fetchJSON("/api/plugins/project-explorer/sessions/" + selectedSession.id + "/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project_path: projectPathInput.trim() })
            })
            .then(function (data) {
                setLinkDialogOpen(false);
                setSelectedSession(null);
                setProjectPathInput("");
                fetchProjects();
                if (data.project) {
                    setSelectedProject(data.project);
                }
            })
            .catch(function (err) {
                console.error("Failed to link project:", err);
                alert("Failed to link project: " + err.message);
            });
        }

        function renderTreeNode(node, depth) {
            if (!node) return null;
            var indent = depth * 16;
            var isDir = node.type === "directory";

            // For directories, check if expanded
            var isExpanded = isDir && node.path && expandedPaths.has(node.path);
            var hasChildren = isDir && node.children && node.children.length > 0;

            var containerStyle = {
                paddingLeft: indent + "px"
            };

            if (isDir) {
                // Directory row - clickable to toggle
                var row = React.createElement("div", {
                    className: cn(
                        "flex items-center gap-1 py-1 text-sm font-medium cursor-pointer hover:bg-foreground/5 rounded px-1",
                        isExpanded && "bg-foreground/5"
                    ),
                    style: containerStyle,
                    onClick: function(e) {
                        e.stopPropagation();
                        if (node.path) {
                            toggleFolder(node.path);
                        }
                    }
                },
                    // Chevron indicator
                    React.createElement("span", {
                        className: cn(
                            "w-4 text-xs text-muted-foreground transition-transform",
                            isExpanded ? "rotate-90" : ""
                        ),
                        style: { display: "inline-block", width: 16 }
                    }, hasChildren ? (isExpanded ? "▼" : "▶") : " "),
                    React.createElement("span", { className: "text-amber-500" }, "\uD83D\uDCC1"),
                    React.createElement("span", null, node.name),
                    hasChildren && React.createElement("span", { className: "text-xs text-muted-foreground ml-1" },
                        "(" + node.children.length + ")"
                    )
                );

                // Render children only if expanded
                if (isExpanded && node.children) {
                    var childrenDiv = React.createElement("div", { className: "" },
                        node.children.map(function(child) {
                            return renderTreeNode(child, depth + 1);
                        })
                    );
                    return React.createElement(React.Fragment, { key: node.path || node.name },
                        row,
                        childrenDiv
                    );
                }

                return row;
            } else {
                // File row - non-clickable
                return React.createElement("div", {
                    key: node.path || node.name,
                    className: cn("flex items-center gap-1 py-1 text-sm text-muted-foreground"),
                    style: containerStyle
                },
                    React.createElement("span", { className: "w-4" }, " "),
                    React.createElement("span", { className: "text-blue-500" }, "\uD83D\uDCC4"),
                    React.createElement("span", null, node.name)
                );
            }
        }

        function formatLastUsed(timestamp) {
            if (!timestamp) return "Never";
            return timeAgo(timestamp * 1000);
        }

        // PE-8-1: Render LOC bar chart
        function renderLocChart(locData) {
            if (!locData || !locData.by_extension || Object.keys(locData.by_extension).length === 0) {
                return React.createElement("div", { className: "text-sm text-muted-foreground" }, "No LOC data available");
            }
            
            var entries = Object.entries(locData.by_extension);
            var total = locData.total || 0;
            var maxCount = Math.max.apply(null, entries.map(function(e) { return e[1]; }));
            
            // Sort by count descending
            entries.sort(function(a, b) { return b[1] - a[1]; });
            
            var bars = entries.slice(0, 10).map(function(entry) {
                var ext = entry[0];
                var count = entry[1];
                var width = maxCount > 0 ? (count / maxCount) * 100 : 0;
                var colorClass = getExtensionColor(ext);
                
                return React.createElement("div", { key: ext, className: "flex items-center gap-2" },
                    React.createElement("span", { className: "w-16 text-xs text-muted-foreground truncate" }, ext),
                    React.createElement("div", { className: "flex-1 bg-muted rounded-sm h-5 relative overflow-hidden" },
                        React.createElement("div", { 
                            className: cn("h-full rounded-sm transition-all", colorClass),
                            style: { width: width + "%" }
                        })
                    ),
                    React.createElement("span", { className: "w-16 text-xs text-right" }, count.toLocaleString())
                );
            });
            
            return React.createElement("div", { className: "space-y-1" },
                React.createElement("div", { className: "text-sm font-medium mb-2" }, "Lines of Code by Extension (Total: " + total.toLocaleString() + ")"),
                bars
            );
        }

        // PE-8-2: Render file type pie chart as colored bars
        function renderFileTypeChart(fileTypes) {
            if (!fileTypes || Object.keys(fileTypes).length === 0) {
                return React.createElement("div", { className: "text-sm text-muted-foreground" }, "No file type data available");
            }
            
            var entries = Object.entries(fileTypes);
            var total = entries.reduce(function(sum, e) { return sum + e[1]; }, 0);
            
            // Sort by count descending
            entries.sort(function(a, b) { return b[1] - a[1]; });
            
            var bars = entries.slice(0, 10).map(function(entry) {
                var ext = entry[0];
                var count = entry[1];
                var percent = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
                var colorClass = getExtensionColor(ext);
                
                return React.createElement("div", { key: ext, className: "flex items-center gap-2" },
                    React.createElement("span", { className: "w-16 text-xs text-muted-foreground truncate" }, ext),
                    React.createElement("div", { className: "flex-1 bg-muted rounded-sm h-5 relative overflow-hidden" },
                        React.createElement("div", { 
                            className: cn("h-full rounded-sm transition-all", colorClass),
                            style: { width: percent + "%" }
                        })
                    ),
                    React.createElement("span", { className: "w-24 text-xs text-right" }, count + " (" + percent + "%)")
                );
            });
            
            return React.createElement("div", { className: "space-y-1" },
                React.createElement("div", { className: "text-sm font-medium mb-2" }, "File Types (Total: " + total + " files)"),
                bars
            );
        }

        // PE-8-3: Render KB search UI
        function renderKbSearch() {
            if (kbStatus && kbStatus.status === "not_started") {
                return React.createElement("div", { className: "p-4 bg-muted/30 rounded-md" },
                    React.createElement("div", { className: "text-sm text-muted-foreground" }, "KB not yet generated")
                );
            }
            
            return React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: "flex gap-2" },
                    React.createElement(Input, {
                        placeholder: "Search knowledge base...",
                        value: kbSearchQuery,
                        onChange: function (e) { setKbSearchQuery(e.target.value); },
                        onKeyDown: function (e) { 
                            if (e.key === "Enter" && selectedProject) {
                                searchKb(selectedProject.id, kbSearchQuery);
                            }
                        },
                        className: "flex-1"
                    }),
                    React.createElement(Button, {
                        size: "sm",
                        onClick: function () { 
                            if (selectedProject) searchKb(selectedProject.id, kbSearchQuery);
                        },
                        disabled: kbSearchLoading || !kbSearchQuery.trim()
                    }, kbSearchLoading ? "..." : "Search")
                ),
                kbSearchResults.length > 0
                    ? React.createElement("div", { className: "space-y-2 max-h-64 overflow-auto" },
                        kbSearchResults.map(function(result, idx) {
                            return React.createElement("div", { key: idx, className: "p-2 bg-muted/30 rounded text-sm" },
                                React.createElement("div", { className: "font-medium text-xs text-muted-foreground mb-1" }, result.section || "Unknown section"),
                                React.createElement("div", { dangerouslySetInnerHTML: { __html: result.matched_content || result.content || "" } })
                            );
                        })
                    )
                    : kbSearchQuery && !kbSearchLoading
                        ? React.createElement("div", { className: "text-sm text-muted-foreground" }, "No results found")
                        : null
            );
        }

        // PE-8-4: Render activity feed
        function renderActivityFeed() {
            if (activityLoading) {
                return React.createElement("div", { className: "text-sm text-muted-foreground" }, "Loading activity...");
            }
            
            if (activityFeed.length === 0) {
                return React.createElement("div", { className: "text-sm text-muted-foreground" }, "No recent activity");
            }
            
            var items = activityFeed.map(function(activity, idx) {
                var timestamp = activity.timestamp ? timeAgo(activity.timestamp * 1000) : "";
                var summary = activity.summary || "Activity recorded";
                var actions = [];
                
                try {
                    var parsedActions = typeof activity.actions === "string" 
                        ? JSON.parse(activity.actions) 
                        : activity.actions;
                    if (Array.isArray(parsedActions)) {
                        actions = parsedActions;
                    }
                } catch (e) {}
                
                return React.createElement("div", { key: idx, className: "border-b border-border py-2 last:border-0" },
                    React.createElement("div", { className: "flex items-center justify-between mb-1" },
                        React.createElement("span", { className: "text-xs text-muted-foreground" }, timestamp),
                        React.createElement("span", { className: "text-xs text-muted-foreground" }, activity.session_id ? activity.session_id.substring(0, 8) : "")
                    ),
                    React.createElement("div", { className: "text-sm" }, summary),
                    actions.length > 0 && React.createElement("div", { className: "mt-1 flex flex-wrap gap-1" },
                        actions.slice(0, 3).map(function(action, aidx) {
                            return React.createElement(Badge, { key: aidx, variant: "secondary", className: "text-xs py-0" }, action);
                        }),
                        actions.length > 3 && React.createElement(Badge, { variant: "secondary", className: "text-xs py-0" }, "+" + (actions.length - 3))
                    )
                );
            });
            
            return React.createElement("div", { className: "space-y-0" }, items);
        }

        // Helper function to get color class for extension
        function getExtensionColor(ext) {
            var colors = [
                "bg-blue-500", "bg-green-500", "bg-yellow-500", "bg-red-500",
                "bg-purple-500", "bg-pink-500", "bg-indigo-500", "bg-orange-500",
                "bg-teal-500", "bg-cyan-500"
            ];
            var hash = 0;
            for (var i = 0; i < ext.length; i++) {
                hash = ((hash << 5) - hash) + ext.charCodeAt(i);
                hash = hash & hash;
            }
            return colors[Math.abs(hash) % colors.length];
        }

        function renderProjectsView() {
            return React.createElement("div", { className: "flex flex-col h-full gap-4" },
                React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                        React.createElement(CardTitle, { className: "text-xl" }, "Projects"),
                        React.createElement(Badge, { variant: "outline" }, projects.length + " projects")
                    ),
                    React.createElement("div", { className: "flex gap-2" },
                        React.createElement(Input, {
                            placeholder: "Search projects...",
                            value: searchQuery,
                            onChange: function (e) { setSearchQuery(e.target.value); },
                            className: "w-64"
                        }),
                        React.createElement(Button, {
                            variant: "outline",
                            size: "sm",
                            onClick: fetchProjects
                        }, "Refresh")
                    )
                ),

                error && React.createElement(Card, { className: "border-red-500" },
                    React.createElement(CardContent, { className: "py-4" },
                        React.createElement("span", { className: "text-red-500" }, error)
                    )
                ),

                loading && React.createElement(Card,
                    React.createElement(CardContent, { className: "py-8 text-center text-muted-foreground" },
                        "Loading projects..."
                    )
                ),

                !loading && React.createElement("div", { className: "flex flex-1 gap-4 min-h-0" },
                    React.createElement(Card, { className: "w-72 flex flex-col" },
                        React.createElement(CardHeader, { className: "pb-2" },
                            React.createElement(CardTitle, { className: "text-sm" }, "All Projects")
                        ),
                        React.createElement(CardContent, { className: "flex-1 overflow-auto p-0" },
                            filteredProjects.length === 0
                                ? React.createElement("div", { className: "p-4 text-sm text-muted-foreground" },
                                    searchQuery ? "No projects match your search" : "No projects yet. Click Sessions to link a session to a project."
                                )
                                : React.createElement("div", { className: "flex flex-col" },
                                    filteredProjects.map(function (project) {
                                        return React.createElement("button", {
                                            key: project.id,
                                            onClick: function () { setSelectedProject(project); },
                                            className: cn(
                                                "text-left p-3 border-b border-border hover:bg-foreground/5 transition-colors",
                                                selectedProject && selectedProject.id === project.id && "bg-foreground/10"
                                            )
                                        },
                                            React.createElement("div", { className: "font-medium text-sm" }, project.name),
                                            React.createElement("div", { className: "text-xs text-muted-foreground truncate" }, project.path),
                                            React.createElement("div", { className: "flex items-center gap-2 mt-1" },
                                                React.createElement("span", { className: "text-xs text-muted-foreground" },
                                                    formatLastUsed(project.last_used)
                                                ),
                                                project.is_git_repo && React.createElement(Badge, { variant: "secondary", className: "text-xs py-0" }, "Git")
                                            )
                                        );
                                    })
                                )
                        )
                    ),

                    React.createElement(Card, { className: "flex-1 flex flex-col" },
                        selectedProject
                            ? React.createElement(React.Fragment, null,
                                React.createElement(CardHeader, { className: "pb-2" },
                                    React.createElement("div", { className: "flex items-center justify-between" },
                                        React.createElement(CardTitle, { className: "text-lg" }, selectedProject.name),
                                        React.createElement("div", { className: "flex gap-2" },
                                            React.createElement(Button, {
                                                variant: "outline",
                                                size: "sm",
                                                onClick: function () { fetchProjectTree(selectedProject.id); }
                                            }, "Refresh")
                                        )
                                    )
                                ),
                                React.createElement(CardContent, { className: "flex-1 overflow-auto" },
                                    React.createElement("div", { className: "mb-4 p-3 bg-muted/30 rounded-md" },
                                        React.createElement("div", { className: "text-sm font-mono mb-2" }, selectedProject.path),
                                        React.createElement("div", { className: "flex gap-4 text-xs text-muted-foreground" },
                                            React.createElement("span", null, "Sessions: " + selectedProject.session_count),
                                            selectedProject.is_git_repo && React.createElement("span", null, "Git: " + (selectedProject.git_remote || "detected")),
                                            React.createElement("span", null, "Last used: " + formatLastUsed(selectedProject.last_used))
                                        )
                                    ),
                                    // PE-8: Add new visualization sections
                                    React.createElement("div", { className: "mb-6" },
                                        React.createElement("div", { className: "flex items-center justify-between mb-3" },
                                            React.createElement("h3", { className: "text-sm font-semibold" }, "Project Statistics"),
                                            statsLoading && React.createElement("span", { className: "text-xs text-muted-foreground" }, "Loading...")
                                        ),
                                        React.createElement("div", { className: "grid grid-cols-2 gap-4" },
                                            // PE-8-1: LOC Chart
                                            React.createElement("div", { className: "p-3 bg-muted/20 rounded-md" },
                                                React.createElement("h4", { className: "text-xs font-medium text-muted-foreground mb-2" }, "Lines of Code"),
                                                statsLoading 
                                                    ? React.createElement("div", { className: "text-xs text-muted-foreground" }, "...")
                                                    : projectStats && projectStats.loc
                                                        ? renderLocChart(projectStats.loc)
                                                        : React.createElement("div", { className: "text-xs text-muted-foreground" }, "Stats not available (404)")
                                            ),
                                            // PE-8-2: File Type Chart
                                            React.createElement("div", { className: "p-3 bg-muted/20 rounded-md" },
                                                React.createElement("h4", { className: "text-xs font-medium text-muted-foreground mb-2" }, "File Types"),
                                                statsLoading 
                                                    ? React.createElement("div", { className: "text-xs text-muted-foreground" }, "...")
                                                    : projectStats && projectStats.file_types
                                                        ? renderFileTypeChart(projectStats.file_types)
                                                        : React.createElement("div", { className: "text-xs text-muted-foreground" }, "Stats not available (404)")
                                            )
                                        ),
                                        projectStats && projectStats.git_status && React.createElement("div", { className: "mt-3 text-xs" },
                                            React.createElement(Badge, { variant: projectStats.git_status === "clean" ? "secondary" : "outline" },
                                                "Git: " + projectStats.git_status
                                            )
                                        )
                                    ),
                                    // PE-8-3: KB Search
                                    React.createElement("div", { className: "mb-6" },
                                        React.createElement("h3", { className: "text-sm font-semibold mb-3" }, "Knowledge Base Search"),
                                        renderKbSearch()
                                    ),
                                    // PE-8-4: Activity Feed
                                    React.createElement("div", { className: "mb-6" },
                                        React.createElement("div", { className: "flex items-center justify-between mb-3" },
                                            React.createElement("h3", { className: "text-sm font-semibold" }, "Activity Feed"),
                                            React.createElement(Button, {
                                                variant: "ghost",
                                                size: "sm",
                                                onClick: function () { fetchActivityFeed(selectedProject.id); }
                                            }, "Refresh")
                                        ),
                                        React.createElement("div", { className: "bg-muted/20 rounded-md p-3" },
                                            renderActivityFeed()
                                        )
                                    ),
                                    // File Tree Section
                                    React.createElement("div", null,
                                        React.createElement("h3", { className: "text-sm font-semibold mb-3" }, "File Tree"),
                                        treeLoading
                                            ? React.createElement("div", { className: "text-sm text-muted-foreground" }, "Loading tree...")
                                            : projectTree
                                                ? React.createElement("div", { className: "font-mono text-sm" },
                                                    renderTreeNode(projectTree, 0)
                                                )
                                                : React.createElement("div", { className: "text-sm text-muted-foreground" },
                                                    "Unable to load project tree"
                                                )
                                    )
                                )
                            )
                            : React.createElement(CardContent, { className: "flex-1 flex items-center justify-center text-muted-foreground" },
                                "Select a project to view its structure"
                            )
                    )
                )
            );
        }

        function renderSessionsView() {
            return React.createElement("div", { className: "flex flex-col h-full gap-4" },
                React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                        React.createElement(CardTitle, { className: "text-xl" }, "Sessions"),
                        React.createElement(Badge, { variant: "outline" }, sessions.length + " active")
                    ),
                    React.createElement(Button, {
                        variant: "outline",
                        size: "sm",
                        onClick: fetchSessions
                    }, "Refresh")
                ),

                React.createElement(Card, { className: "flex-1" },
                    React.createElement(CardContent, { className: "p-0" },
                        sessions.length === 0
                            ? React.createElement("div", { className: "p-4 text-sm text-muted-foreground" },
                                "No active sessions. Start a session from the CLI or gateway to link it to a project."
                            )
                            : React.createElement("div", { className: "flex flex-col" },
                                sessions.map(function (session) {
                                    return React.createElement("div", {
                                        key: session.id,
                                        className: "flex items-center justify-between p-3 border-b border-border"
                                    },
                                        React.createElement("div", { className: "flex-1" },
                                            React.createElement("div", { className: "font-medium text-sm" },
                                                session.project_name || session.id.substring(0, 8)
                                            ),
                                            React.createElement("div", { className: "text-xs text-muted-foreground" },
                                                session.project_path || "No working directory"
                                            )
                                        ),
                                        React.createElement(Button, {
                                            size: "sm",
                                            onClick: function () { handleLinkSession(session); }
                                        }, "Link to Project")
                                    );
                                })
                            )
                    )
                ),

                React.createElement("div", { className: "text-sm text-muted-foreground" },
                    "Click 'Link to Project' to associate a session with a repository. The project will be tracked and its file structure will be available."
                )
            );
        }

        return React.createElement("div", { className: "flex flex-col h-full" },
            React.createElement("div", { className: "flex gap-2 mb-4" },
                React.createElement(Button, {
                    variant: view === "projects" ? "default" : "outline",
                    size: "sm",
                    onClick: function () { setView("projects"); }
                }, "Projects"),
                React.createElement(Button, {
                    variant: view === "sessions" ? "default" : "outline",
                    size: "sm",
                    onClick: function () { setView("sessions"); }
                }, "Sessions")
            ),

view === "projects" ? renderProjectsView() : renderSessionsView(),

  linkDialogOpen && React.createElement("div", {
    className: "fixed inset-0 bg-black/50 flex items-center justify-center z-50",
    onClick: function (e) { if (e.target === e.currentTarget) setLinkDialogOpen(false); }
  },
    React.createElement("div", {
      className: "bg-background border border-border rounded-lg shadow-lg w-full max-w-md mx-4",
      onClick: function (e) { e.stopPropagation(); }
    },
      React.createElement("div", { className: "p-4 border-b border-border" },
        React.createElement("h2", { className: "text-lg font-semibold" }, "Link Session to Project"),
        React.createElement("p", { className: "text-sm text-muted-foreground mt-1" }, "Enter the root directory path of the project this session is working on.")
      ),
      React.createElement("form", {
        onSubmit: function (e) { e.preventDefault(); submitLinkProject(); },
        className: "p-4"
      },
        React.createElement(Input, {
          placeholder: "/path/to/project",
          value: projectPathInput,
          onChange: function (e) { setProjectPathInput(e.target.value); },
          className: "w-full"
        }),
        selectedSession && selectedSession.cwd && React.createElement("div", { className: "mt-2 text-xs text-muted-foreground" }, "Current session cwd: ", selectedSession.cwd),
        React.createElement("div", { className: "flex justify-end gap-2 mt-4" },
          React.createElement(Button, {
            type: "button",
            variant: "outline",
            onClick: function () { setLinkDialogOpen(false); }
          }, "Cancel"),
          React.createElement(Button, {
            type: "submit",
            disabled: !projectPathInput.trim()
          }, "Link Project")
        )
      )
    )
  )
);
}

    window.__HERMES_PLUGINS__.register("project-explorer", ProjectsPage);
})();