import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  CollapsibleSection,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Link,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

type Problem = "islands" | "oranges" | "ladder" | "surrounded" | "cycle";
type PanelMode = "problem" | "walk" | "solution";
type Company = "all" | "google" | "microsoft" | "amazon";

const ISLAND_GRID = [
  [1, 1, 0, 0, 0],
  [1, 1, 0, 0, 0],
  [0, 0, 1, 0, 0],
  [0, 0, 0, 1, 1],
];

const ORANGE_STEPS = [
  {
    minute: 0,
    grid: [
      [2, 1, 1],
      [1, 1, 0],
      [0, 1, 1],
    ],
    note: "Minute 0 — seed every rotten orange into the queue",
  },
  {
    minute: 1,
    grid: [
      [2, 2, 1],
      [2, 1, 0],
      [0, 1, 1],
    ],
    note: "Minute 1 — all neighbors of the original rotten orange rot together",
  },
  {
    minute: 2,
    grid: [
      [2, 2, 2],
      [2, 2, 0],
      [0, 1, 1],
    ],
    note: "Minute 2 — infection spreads another ring outward",
  },
  {
    minute: 3,
    grid: [
      [2, 2, 2],
      [2, 2, 0],
      [0, 2, 1],
    ],
    note: "Minute 3 — bottom-middle orange rots",
  },
  {
    minute: 4,
    grid: [
      [2, 2, 2],
      [2, 2, 0],
      [0, 2, 2],
    ],
    note: "Minute 4 — last fresh orange rots. Answer = 4",
  },
];

const LADDER_PATH = [
  { word: "hit", change: "start" },
  { word: "hot", change: "i→o" },
  { word: "dot", change: "h→d" },
  { word: "dog", change: "t→g" },
  { word: "cog", change: "d→c · end" },
];

const FAANG_PROBLEMS: {
  name: string;
  lc: string;
  pattern: string;
  like: string;
  companies: ("google" | "microsoft" | "amazon")[];
  why: string;
  hint: string;
}[] = [
  {
    name: "Max Area of Island",
    lc: "LC 695",
    pattern: "count components",
    like: "Islands",
    companies: ["amazon", "microsoft"],
    why: "Same flood-fill, but return the largest island size instead of the count.",
    hint: "DFS returns area; track max while scanning.",
  },
  {
    name: "Number of Provinces",
    lc: "LC 547",
    pattern: "count components",
    like: "Islands",
    companies: ["amazon", "google", "microsoft"],
    why: "Islands on an adjacency matrix instead of a grid.",
    hint: "DFS/BFS or Union-Find over n cities.",
  },
  {
    name: "Flood Fill",
    lc: "LC 733",
    pattern: "count components",
    like: "Islands",
    companies: ["amazon", "microsoft"],
    why: "Paint one connected component starting from a given cell.",
    hint: "Classic DFS/BFS flood from (sr, sc).",
  },
  {
    name: "Surrounded Regions",
    lc: "LC 130",
    pattern: "count components",
    like: "Islands",
    companies: ["amazon", "google", "microsoft"],
    why: "Capture O regions that cannot touch the border — flood from borders first.",
    hint: "Mark border-connected O's safe, then flip the rest.",
  },
  {
    name: "Pacific Atlantic Water Flow",
    lc: "LC 417",
    pattern: "multi-source BFS",
    like: "Oranges",
    companies: ["amazon", "google"],
    why: "Two oceans = two multi-source BFS/DFS; answer is intersection.",
    hint: "Start from both ocean borders; cells reachable by both win.",
  },
  {
    name: "01 Matrix",
    lc: "LC 542",
    pattern: "multi-source BFS",
    like: "Oranges",
    companies: ["amazon", "google", "microsoft"],
    why: "Distance from every cell to nearest 0 — seed all 0s into the queue.",
    hint: "Same as rotting oranges, but distance to zeros.",
  },
  {
    name: "Walls and Gates",
    lc: "LC 286",
    pattern: "multi-source BFS",
    like: "Oranges",
    companies: ["amazon", "google", "microsoft"],
    why: "Fill each empty room with distance to nearest gate.",
    hint: "Enqueue all gates (0); BFS fills INF rooms.",
  },
  {
    name: "Shortest Bridge",
    lc: "LC 934",
    pattern: "multi-source BFS",
    like: "Oranges + Islands",
    companies: ["amazon", "google"],
    why: "Paint island A, then multi-source BFS until you touch island B.",
    hint: "DFS collect island 1 → BFS expand water until island 2.",
  },
  {
    name: "Shortest Path in Binary Matrix",
    lc: "LC 1091",
    pattern: "shortest path BFS",
    like: "Word Ladder",
    companies: ["amazon", "microsoft", "google"],
    why: "Grid shortest path; 8 directions allowed here.",
    hint: "BFS from (0,0) to (n-1,n-1); return length or -1.",
  },
  {
    name: "Word Search",
    lc: "LC 79",
    pattern: "DFS backtrack",
    like: "Islands / Ladder",
    companies: ["amazon", "microsoft", "google"],
    why: "Find a word path on a grid — DFS with mark/unmark.",
    hint: "Backtracking; restore cell after exploring.",
  },
  {
    name: "Open the Lock",
    lc: "LC 752",
    pattern: "shortest path BFS",
    like: "Word Ladder",
    companies: ["amazon", "google"],
    why: "4-digit lock; each turn ±1 on one wheel — same as mutating a word.",
    hint: "BFS from '0000'; skip deadends; 8 neighbors per state.",
  },
  {
    name: "Minimum Knight Moves",
    lc: "LC 1197",
    pattern: "shortest path BFS",
    like: "Word Ladder",
    companies: ["amazon", "google", "microsoft"],
    why: "Chess knight = graph node; BFS to (x,y).",
    hint: "BFS on infinite board; prune with abs coords symmetry.",
  },
  {
    name: "Keys and Rooms",
    lc: "LC 841",
    pattern: "count components",
    like: "Islands",
    companies: ["amazon", "google", "microsoft"],
    why: "Can you visit all rooms starting from 0? Reachability DFS/BFS.",
    hint: "Start at room 0; collect keys; visit all?",
  },
  {
    name: "Course Schedule",
    lc: "LC 207",
    pattern: "graph BFS/DFS",
    like: "Word Ladder graph",
    companies: ["amazon", "google", "microsoft"],
    why: "Detect cycle in directed graph (prerequisites).",
    hint: "DFS coloring or Kahn's BFS topological sort.",
  },
  {
    name: "Clone Graph",
    lc: "LC 133",
    pattern: "graph BFS/DFS",
    like: "Islands traversal",
    companies: ["amazon", "google", "microsoft"],
    why: "Traverse + copy nodes; map old→new while BFS/DFS.",
    hint: "HashMap visited; clone neighbors recursively or with queue.",
  },
  {
    name: "Swim in Rising Water",
    lc: "LC 778",
    pattern: "shortest path BFS",
    like: "Oranges / Ladder",
    companies: ["amazon", "google"],
    why: "Minimize max height on path — binary search + BFS, or Dijkstra.",
    hint: "Check if you can reach end when water ≤ mid.",
  },
];

const FAANG_SOLUTIONS: Record<
  string,
  {
    code: string;
    iterative?: string;
    bullets: string[];
    time: string;
    space: string;
  }
> = {
  "Max Area of Island": {
    bullets: ["Same flood-fill as Islands; return max area instead of count.", "Prefer Queue/Stack — recursive DFS can overflow on a huge island.", "Mark visited when enqueueing (set cell to 0).", "Time O(R·C), heap space O(R·C)."],
    time: 'O(R · C)',
    space: 'O(R · C) queue/stack',
    iterative: `import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public int maxAreaOfIsland(int[][] grid) {
        int max = 0, rows = grid.length, cols = grid[0].length;
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (grid[r][c] == 1) max = Math.max(max, flood(grid, r, c));
            }
        }
        return max;
    }

    private int flood(int[][] grid, int sr, int sc) {
        int rows = grid.length, cols = grid[0].length, area = 0;
        Queue<int[]> q = new ArrayDeque<>();
        q.offer(new int[]{sr, sc});
        grid[sr][sc] = 0;
        while (!q.isEmpty()) {
            int[] cur = q.poll();
            area++;
            for (int[] d : DIRS) {
                int nr = cur[0] + d[0], nc = cur[1] + d[1];
                if (nr < 0 || nc < 0 || nr >= rows || nc >= cols || grid[nr][nc] == 0) continue;
                grid[nr][nc] = 0;
                q.offer(new int[]{nr, nc});
            }
        }
        return area;
    }
}`,
    code: `// Recursive (small grids only)
class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};
    public int maxAreaOfIsland(int[][] grid) {
        int max = 0;
        for (int r = 0; r < grid.length; r++)
            for (int c = 0; c < grid[0].length; c++)
                if (grid[r][c] == 1) max = Math.max(max, dfs(grid, r, c));
        return max;
    }
    private int dfs(int[][] grid, int r, int c) {
        if (r < 0 || c < 0 || r >= grid.length || c >= grid[0].length || grid[r][c] == 0) return 0;
        grid[r][c] = 0;
        int area = 1;
        for (int[] d : DIRS) area += dfs(grid, r + d[0], c + d[1]);
        return area;
    }
}`,
  },
  "Number of Provinces": {
    bullets: ["Adjacency matrix graph — each unvisited city starts a province.", "Use BFS/Stack instead of recursive DFS for large n.", "Count how many times you start a new flood.", "Union-Find is another solid option."],
    time: 'O(n²)',
    space: 'O(n) visited + queue',
    iterative: `import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    public int findCircleNum(int[][] isConnected) {
        int n = isConnected.length;
        boolean[] visited = new boolean[n];
        int provinces = 0;
        for (int i = 0; i < n; i++) {
            if (visited[i]) continue;
            provinces++;
            Queue<Integer> q = new ArrayDeque<>();
            q.offer(i);
            visited[i] = true;
            while (!q.isEmpty()) {
                int node = q.poll();
                for (int j = 0; j < n; j++) {
                    if (isConnected[node][j] == 1 && !visited[j]) {
                        visited[j] = true;
                        q.offer(j);
                    }
                }
            }
        }
        return provinces;
    }
}`,
    code: `// Recursive DFS (fine for typical n ≤ 200)
class Solution {
    public int findCircleNum(int[][] isConnected) {
        int n = isConnected.length;
        boolean[] visited = new boolean[n];
        int provinces = 0;
        for (int i = 0; i < n; i++) {
            if (!visited[i]) {
                provinces++;
                dfs(isConnected, visited, i);
            }
        }
        return provinces;
    }
    private void dfs(int[][] g, boolean[] visited, int node) {
        visited[node] = true;
        for (int j = 0; j < g.length; j++)
            if (g[node][j] == 1 && !visited[j]) dfs(g, visited, j);
    }
}`,
  },
  "Flood Fill": {
    bullets: ["Paint-bucket: flood cells matching original color.", "Iterative BFS avoids deep recursion on large regions.", "Early return if new color equals original.", "Mark/paint when enqueueing."],
    time: 'O(R · C)',
    space: 'O(R · C) queue',
    iterative: `import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public int[][] floodFill(int[][] image, int sr, int sc, int color) {
        int orig = image[sr][sc];
        if (orig == color) return image;
        int rows = image.length, cols = image[0].length;
        Queue<int[]> q = new ArrayDeque<>();
        q.offer(new int[]{sr, sc});
        image[sr][sc] = color;
        while (!q.isEmpty()) {
            int[] cur = q.poll();
            for (int[] d : DIRS) {
                int nr = cur[0] + d[0], nc = cur[1] + d[1];
                if (nr < 0 || nc < 0 || nr >= rows || nc >= cols
                        || image[nr][nc] != orig) continue;
                image[nr][nc] = color;
                q.offer(new int[]{nr, nc});
            }
        }
        return image;
    }
}`,
    code: `// Recursive (small images only)
class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};
    public int[][] floodFill(int[][] image, int sr, int sc, int color) {
        int orig = image[sr][sc];
        if (orig == color) return image;
        dfs(image, sr, sc, orig, color);
        return image;
    }
    private void dfs(int[][] image, int r, int c, int orig, int color) {
        if (r < 0 || c < 0 || r >= image.length || c >= image[0].length
                || image[r][c] != orig) return;
        image[r][c] = color;
        for (int[] d : DIRS) dfs(image, r + d[0], c + d[1], orig, color);
    }
}`,
  },
  "Surrounded Regions": {
    bullets: ["Regions touching the border can never be captured.", "Mark border-connected 'O's as 'S' (safe) via DFS.", "Remaining 'O's are surrounded \u2192 flip to 'X'.", "Restore safe cells back to 'O'."],
    time: 'O(R · C)',
    space: 'O(R · C)',
    iterative: `import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    private static final int[][] DIRS = {{1,0},{-1,0},{0,1},{0,-1}};
    public void solve(char[][] board) {
        if (board == null || board.length == 0) return;
        int rows = board.length, cols = board[0].length;
        Queue<int[]> q = new ArrayDeque<>();
        for (int r = 0; r < rows; r++) {
            if (board[r][0] == 'O') { board[r][0] = 'S'; q.offer(new int[]{r,0}); }
            if (board[r][cols-1] == 'O') { board[r][cols-1] = 'S'; q.offer(new int[]{r,cols-1}); }
        }
        for (int c = 0; c < cols; c++) {
            if (board[0][c] == 'O') { board[0][c] = 'S'; q.offer(new int[]{0,c}); }
            if (board[rows-1][c] == 'O') { board[rows-1][c] = 'S'; q.offer(new int[]{rows-1,c}); }
        }
        while (!q.isEmpty()) {
            int[] cur = q.poll();
            for (int[] d : DIRS) {
                int nr = cur[0]+d[0], nc = cur[1]+d[1];
                if (nr<0||nc<0||nr>=rows||nc>=cols||board[nr][nc]!='O') continue;
                board[nr][nc] = 'S';
                q.offer(new int[]{nr,nc});
            }
        }
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++) {
                if (board[r][c] == 'O') board[r][c] = 'X';
                else if (board[r][c] == 'S') board[r][c] = 'O';
            }
    }
}`,
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public void solve(char[][] board) {
        if (board == null || board.length == 0) return;
        int rows = board.length, cols = board[0].length;
        for (int r = 0; r < rows; r++) {
            if (board[r][0] == 'O') dfs(board, r, 0);
            if (board[r][cols - 1] == 'O') dfs(board, r, cols - 1);
        }
        for (int c = 0; c < cols; c++) {
            if (board[0][c] == 'O') dfs(board, 0, c);
            if (board[rows - 1][c] == 'O') dfs(board, rows - 1, c);
        }
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (board[r][c] == 'O') board[r][c] = 'X';
                else if (board[r][c] == 'S') board[r][c] = 'O';
            }
        }
    }

    private void dfs(char[][] board, int r, int c) {
        if (r < 0 || c < 0 || r >= board.length || c >= board[0].length
                || board[r][c] != 'O') return;
        board[r][c] = 'S'; // safe
        for (int[] d : DIRS) dfs(board, r + d[0], c + d[1]);
    }
}`,
  },
  "Pacific Atlantic Water Flow": {
    bullets: ["Water flows uphill in reverse: from ocean inward to higher/equal cells.", "Run DFS from Pacific borders and Atlantic borders separately.", "Intersection of both reachable sets is the answer.", "Avoids TLE from checking every cell forward to both oceans."],
    time: 'O(R · C)',
    space: 'O(R · C)',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public List<List<Integer>> pacificAtlantic(int[][] heights) {
        int rows = heights.length, cols = heights[0].length;
        boolean[][] pacific = new boolean[rows][cols];
        boolean[][] atlantic = new boolean[rows][cols];
        for (int c = 0; c < cols; c++) {
            dfs(heights, pacific, 0, c);
            dfs(heights, atlantic, rows - 1, c);
        }
        for (int r = 0; r < rows; r++) {
            dfs(heights, pacific, r, 0);
            dfs(heights, atlantic, r, cols - 1);
        }
        List<List<Integer>> result = new ArrayList<>();
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (pacific[r][c] && atlantic[r][c]) {
                    result.add(Arrays.asList(r, c));
                }
            }
        }
        return result;
    }

    private void dfs(int[][] heights, boolean[][] reachable, int r, int c) {
        if (reachable[r][c]) return;
        reachable[r][c] = true;
        for (int[] d : DIRS) {
            int nr = r + d[0], nc = c + d[1];
            if (nr >= 0 && nc >= 0 && nr < heights.length && nc < heights[0].length
                    && heights[nr][nc] >= heights[r][c]) {
                dfs(heights, reachable, nr, nc);
            }
        }
    }
}`,
  },
  "01 Matrix": {
    bullets: ["Seed BFS with every zero cell at distance 0.", "Identical multi-source pattern to Rotting Oranges.", "Relax distances as BFS expands outward.", "Time O(m\u00b7n), each cell enqueued at most once per improvement."],
    time: 'O(R · C)',
    space: 'O(R · C) queue',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public int[][] updateMatrix(int[][] mat) {
        int rows = mat.length, cols = mat[0].length;
        int[][] dist = new int[rows][cols];
        ArrayDeque<int[]> q = new ArrayDeque<>();
        for (int r = 0; r < rows; r++) {
            Arrays.fill(dist[r], Integer.MAX_VALUE);
            for (int c = 0; c < cols; c++) {
                if (mat[r][c] == 0) {
                    dist[r][c] = 0;
                    q.offer(new int[]{r, c});
                }
            }
        }
        while (!q.isEmpty()) {
            int[] cell = q.poll();
            for (int[] d : DIRS) {
                int nr = cell[0] + d[0], nc = cell[1] + d[1];
                if (nr >= 0 && nc >= 0 && nr < rows && nc < cols
                        && dist[nr][nc] > dist[cell[0]][cell[1]] + 1) {
                    dist[nr][nc] = dist[cell[0]][cell[1]] + 1;
                    q.offer(new int[]{nr, nc});
                }
            }
        }
        return dist;
    }
}`,
  },
  "Walls and Gates": {
    bullets: ["Gates are BFS sources at distance 0.", "Skip walls (-1) and already-filled rooms.", "Mutate grid in-place with distances.", "Same orange-spread template with multiple starting points."],
    time: 'O(R · C)',
    space: 'O(R · C) queue',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};
    private static final int INF = Integer.MAX_VALUE;
    private static final int GATE = 0;
    private static final int WALL = -1;

    public void wallsAndGates(int[][] rooms) {
        int rows = rooms.length, cols = rooms[0].length;
        ArrayDeque<int[]> q = new ArrayDeque<>();
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (rooms[r][c] == GATE) q.offer(new int[]{r, c});
            }
        }
        while (!q.isEmpty()) {
            int[] cell = q.poll();
            for (int[] d : DIRS) {
                int nr = cell[0] + d[0], nc = cell[1] + d[1];
                if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue;
                if (rooms[nr][nc] != INF) continue;
                rooms[nr][nc] = rooms[cell[0]][cell[1]] + 1;
                q.offer(new int[]{nr, nc});
            }
        }
    }
}`,
  },
  "Shortest Bridge": {
    bullets: ["Phase 1: DFS marks entire first island as 2 and seeds the queue.", "Phase 2: BFS expands from island border into water (0-cells).", "First time you hit a 1-cell (second island), return step count.", "Combines island flood-fill with multi-source BFS."],
    time: 'O(R · C)',
    space: 'O(R · C)',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public int shortestBridge(int[][] grid) {
        int rows = grid.length, cols = grid[0].length;
        ArrayDeque<int[]> q = new ArrayDeque<>();
        boolean found = false;
        for (int r = 0; r < rows && !found; r++) {
            for (int c = 0; c < cols && !found; c++) {
                if (grid[r][c] == 1) {
                    dfs(grid, r, c, q);
                    found = true;
                }
            }
        }
        int steps = 0;
        while (!q.isEmpty()) {
            int size = q.size();
            for (int i = 0; i < size; i++) {
                int[] cell = q.poll();
                for (int[] d : DIRS) {
                    int nr = cell[0] + d[0], nc = cell[1] + d[1];
                    if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue;
                    if (grid[nr][nc] == 1) return steps;
                    if (grid[nr][nc] == 0) {
                        grid[nr][nc] = 2;
                        q.offer(new int[]{nr, nc});
                    }
                }
            }
            steps++;
        }
        return -1;
    }

    private void dfs(int[][] grid, int r, int c, ArrayDeque<int[]> q) {
        if (r < 0 || c < 0 || r >= grid.length || c >= grid[0].length
                || grid[r][c] != 1) return;
        grid[r][c] = 2;
        q.offer(new int[]{r, c});
        for (int[] d : DIRS) dfs(grid, r + d[0], c + d[1], q);
    }
}`,
  },
  "Shortest Path in Binary Matrix": {
    bullets: ["BFS guarantees shortest path in unweighted grid.", "8 directions including diagonals.", "Mark visited by flipping 0 \u2192 1.", "Level-by-level counting gives path length."],
    time: 'O(R · C)',
    space: 'O(R · C) queue',
    code: `class Solution {
    private static final int[][] DIRS = {
        {-1,-1},{-1,0},{-1,1},{0,-1},{0,1},{1,-1},{1,0},{1,1}
    };

    public int shortestPathBinaryMatrix(int[][] grid) {
        int n = grid.length;
        if (grid[0][0] == 1 || grid[n - 1][n - 1] == 1) return -1;
        if (n == 1) return 1;
        ArrayDeque<int[]> q = new ArrayDeque<>();
        q.offer(new int[]{0, 0});
        grid[0][0] = 1; // visited
        int steps = 1;
        while (!q.isEmpty()) {
            int size = q.size();
            for (int i = 0; i < size; i++) {
                int[] cell = q.poll();
                for (int[] d : DIRS) {
                    int nr = cell[0] + d[0], nc = cell[1] + d[1];
                    if (nr < 0 || nc < 0 || nr >= n || nc >= n || grid[nr][nc] == 1) continue;
                    if (nr == n - 1 && nc == n - 1) return steps + 1;
                    grid[nr][nc] = 1;
                    q.offer(new int[]{nr, nc});
                }
            }
            steps++;
        }
        return -1;
    }
}`,
  },
  "Word Search": {
    bullets: ["Try DFS from every cell as a potential start.", "Mark visited with '#' to prevent reuse in same path.", "Backtrack by restoring character after exploring.", "Prune when character mismatch or out of bounds."],
    time: 'O(R · C · 3^L)',
    space: 'O(L) recursion depth',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public boolean exist(char[][] board, String word) {
        int rows = board.length, cols = board[0].length;
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (dfs(board, word, r, c, 0)) return true;
            }
        }
        return false;
    }

    private boolean dfs(char[][] board, String word, int r, int c, int idx) {
        if (idx == word.length()) return true;
        if (r < 0 || c < 0 || r >= board.length || c >= board[0].length) return false;
        if (board[r][c] != word.charAt(idx)) return false;
        char temp = board[r][c];
        board[r][c] = '#';
        for (int[] d : DIRS) {
            if (dfs(board, word, r + d[0], c + d[1], idx + 1)) return true;
        }
        board[r][c] = temp;
        return false;
    }
}`,
  },
  "Open the Lock": {
    bullets: ["Each lock combination is a node; 8 neighbors (4 wheels \u00d7 2 directions).", "BFS finds minimum moves to target.", "Deadends are blocked nodes \u2014 skip them.", "Modulo arithmetic handles wrap-around (9\u21920, 0\u21929)."],
    time: 'O(10⁴ · 8) = O(1) for 4 wheels',
    space: 'O(10⁴) visited',
    code: `class Solution {
    public int openLock(String[] deadends, String target) {
        Set<String> dead = new HashSet<>(Arrays.asList(deadends));
        String start = "0000";
        if (dead.contains(start)) return -1;
        if (start.equals(target)) return 0;
        ArrayDeque<String> q = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        q.offer(start);
        visited.add(start);
        int moves = 0;
        while (!q.isEmpty()) {
            int size = q.size();
            for (int i = 0; i < size; i++) {
                String cur = q.poll();
                for (int pos = 0; pos < 4; pos++) {
                    for (int delta : new int[]{-1, 1}) {
                        char[] chars = cur.toCharArray();
                        chars[pos] = (char) ((chars[pos] - '0' + delta + 10) % 10 + '0');
                        String next = new String(chars);
                        if (next.equals(target)) return moves + 1;
                        if (dead.contains(next) || visited.contains(next)) continue;
                        visited.add(next);
                        q.offer(next);
                    }
                }
            }
            moves++;
        }
        return -1;
    }
}`,
  },
  "Minimum Knight Moves": {
    bullets: ["Symmetry: work in first quadrant via absolute values.", "BFS from (0,0) outward guarantees minimum moves.", "8 fixed knight move offsets.", "Allow nr/nc \u2265 -1 to handle negative quadrants correctly."],
    time: 'O(max(|x|,|y|)²) typical',
    space: 'O(max(|x|,|y|)²) visited',
    code: `class Solution {
    private static final int[][] MOVES = {
        {2,1},{2,-1},{-2,1},{-2,-1},{1,2},{1,-2},{-1,2},{-1,-2}
    };

    public int minKnightMoves(int x, int y) {
        x = Math.abs(x);
        y = Math.abs(y);
        ArrayDeque<int[]> q = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        q.offer(new int[]{0, 0});
        visited.add("0,0");
        int steps = 0;
        while (!q.isEmpty()) {
            int size = q.size();
            for (int i = 0; i < size; i++) {
                int[] cell = q.poll();
                if (cell[0] == x && cell[1] == y) return steps;
                for (int[] m : MOVES) {
                    int nr = cell[0] + m[0], nc = cell[1] + m[1];
                    if (nr < -1 || nc < -1) continue;
                    String key = nr + "," + nc;
                    if (visited.contains(key)) continue;
                    visited.add(key);
                    q.offer(new int[]{nr, nc});
                }
            }
            steps++;
        }
        return -1;
    }
}`,
  },
  "Keys and Rooms": {
    bullets: ["Rooms form a directed graph; keys are edges.", "DFS from room 0 collects all reachable rooms.", "Return true iff every room was visited.", "BFS with a queue is equally valid."],
    time: 'O(N + E)',
    space: 'O(N)',
    code: `class Solution {
    public boolean canVisitAllRooms(List<List<Integer>> rooms) {
        boolean[] visited = new boolean[rooms.size()];
        dfs(rooms, visited, 0);
        for (boolean v : visited) {
            if (!v) return false;
        }
        return true;
    }

    private void dfs(List<List<Integer>> rooms, boolean[] visited, int room) {
        visited[room] = true;
        for (int key : rooms.get(room)) {
            if (!visited[key]) dfs(rooms, visited, key);
        }
    }
}`,
  },
  "Course Schedule": {
    bullets: ["Build adjacency list and indegree array from prerequisites.", "Kahn's algorithm: BFS courses with indegree 0.", "Decrement indegree when a prerequisite is satisfied.", "Cycle exists iff taken < numCourses (not all courses reachable)."],
    time: 'O(V + E)',
    space: 'O(V + E)',
    code: `class Solution {
    public boolean canFinish(int numCourses, int[][] prerequisites) {
        List<List<Integer>> graph = new ArrayList<>();
        int[] indegree = new int[numCourses];
        for (int i = 0; i < numCourses; i++) graph.add(new ArrayList<>());
        for (int[] pre : prerequisites) {
            graph.get(pre[1]).add(pre[0]);
            indegree[pre[0]]++;
        }
        ArrayDeque<Integer> q = new ArrayDeque<>();
        for (int i = 0; i < numCourses; i++) {
            if (indegree[i] == 0) q.offer(i);
        }
        int taken = 0;
        while (!q.isEmpty()) {
            int course = q.poll();
            taken++;
            for (int next : graph.get(course)) {
                if (--indegree[next] == 0) q.offer(next);
            }
        }
        return taken == numCourses;
    }
}`,
  },
  "Clone Graph": {
    bullets: ["BFS visits all nodes reachable from the start.", "HashMap maps original node \u2192 cloned node.", "Create clone on first discovery; wire neighbors via map lookup.", "DFS with same map pattern is equally common in interviews."],
    time: 'O(N + E)',
    space: 'O(N) map + queue',
    code: `/*
// Definition for a Node.
class Node {
    public int val;
    public List<Node> neighbors;
    public Node() { val = 0; neighbors = new ArrayList<Node>(); }
    public Node(int _val) { val = _val; neighbors = new ArrayList<Node>(); }
    public Node(int _val, ArrayList<Node> _neighbors) {
        val = _val; neighbors = _neighbors;
    }
}
*/

class Solution {
    public Node cloneGraph(Node node) {
        if (node == null) return null;
        Map<Node, Node> map = new HashMap<>();
        ArrayDeque<Node> q = new ArrayDeque<>();
        q.offer(node);
        map.put(node, new Node(node.val));
        while (!q.isEmpty()) {
            Node cur = q.poll();
            for (Node neighbor : cur.neighbors) {
                if (!map.containsKey(neighbor)) {
                    map.put(neighbor, new Node(neighbor.val));
                    q.offer(neighbor);
                }
                map.get(cur).neighbors.add(map.get(neighbor));
            }
        }
        return map.get(node);
    }
}`,
  },
  "Swim in Rising Water": {
    bullets: ["Answer is the minimum time T when a path from top-left to bottom-right exists.", "Binary search T in [max(start,end), n\u00b2-1].", "For each T, BFS checks reachability using cells with height \u2264 T.", "Dijkstra is an alternative but binary search + BFS is simpler to explain.", "Time O(n\u00b2 log n\u00b2) with BFS O(n\u00b2) per check."],
    time: 'O(n² log n)',
    space: 'O(n²)',
    code: `class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};

    public int swimInWater(int[][] grid) {
        int n = grid.length;
        int lo = Math.max(grid[0][0], grid[n - 1][n - 1]);
        int hi = n * n - 1;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (canSwim(grid, mid)) hi = mid;
            else lo = mid + 1;
        }
        return lo;
    }

    private boolean canSwim(int[][] grid, int t) {
        int n = grid.length;
        if (grid[0][0] > t || grid[n - 1][n - 1] > t) return false;
        boolean[][] visited = new boolean[n][n];
        ArrayDeque<int[]> q = new ArrayDeque<>();
        q.offer(new int[]{0, 0});
        visited[0][0] = true;
        while (!q.isEmpty()) {
            int[] cell = q.poll();
            if (cell[0] == n - 1 && cell[1] == n - 1) return true;
            for (int[] d : DIRS) {
                int nr = cell[0] + d[0], nc = cell[1] + d[1];
                if (nr >= 0 && nc >= 0 && nr < n && nc < n
                        && !visited[nr][nc] && grid[nr][nc] <= t) {
                    visited[nr][nc] = true;
                    q.offer(new int[]{nr, nc});
                }
            }
        }
        return false;
    }
}`,
  },
};

function CodeBlock({ children }: { children: string }) {
  const theme = useHostTheme();
  return (
    <pre
      style={{
        margin: 0,
        padding: 12,
        background: theme.fill.tertiary,
        color: theme.text.primary,
        fontSize: 12,
        lineHeight: 1.5,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        borderRadius: 6,
        overflow: "auto",
        whiteSpace: "pre-wrap",
        border: `1px solid ${theme.stroke.tertiary}`,
      }}
    >
      {children}
    </pre>
  );
}

function GridCell({
  value,
  kind,
}: {
  value: number;
  kind: "island" | "orange";
}) {
  const theme = useHostTheme();
  let bg = theme.fill.tertiary;
  let fg = theme.text.tertiary;
  let text = "0";

  if (kind === "island") {
    if (value === 1) {
      bg = theme.accent.primary;
      fg = theme.text.onAccent;
      text = "1";
    } else if (value === 9) {
      bg = theme.fill.secondary;
      fg = theme.text.secondary;
      text = "✓";
    } else {
      text = "0";
    }
  } else {
    if (value === 2) {
      bg = theme.accent.primary;
      fg = theme.text.onAccent;
      text = "R";
    } else if (value === 1) {
      bg = theme.fill.secondary;
      fg = theme.text.primary;
      text = "F";
    } else {
      text = "·";
    }
  }

  return (
    <div
      style={{
        width: 36,
        height: 36,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: bg,
        color: fg,
        fontSize: 13,
        fontWeight: 600,
        borderRadius: 4,
        border: `1px solid ${theme.stroke.tertiary}`,
      }}
    >
      {text}
    </div>
  );
}

function MiniGrid({
  grid,
  kind,
}: {
  grid: number[][];
  kind: "island" | "orange";
}) {
  return (
    <Stack gap={4}>
      {grid.map((row, r) => (
        <div key={r} style={{ display: "flex", gap: 4 }}>
          {row.map((cell, c) => (
            <div key={`${r}-${c}`}>
              <GridCell value={cell} kind={kind} />
            </div>
          ))}
        </div>
      ))}
    </Stack>
  );
}


function ComplexityBadge({ time, space }: { time: string; space: string }) {
  return (
    <Row gap={16} wrap>
      <Stat value={time} label="Time" tone="info" />
      <Stat value={space} label="Space" />
    </Row>
  );
}

function MasterKey() {
  const theme = useHostTheme();
  return (
    <Card>
      <CardHeader trailing={<Pill tone="info">Never forget this</Pill>}>
        The ONE idea behind the core set
      </CardHeader>
      <CardBody>
        <Stack gap={16}>
          <Text weight="semibold">
            They are all graphs. Grids, dictionaries, and course lists are just
            pictures of nodes and edges.
          </Text>
          <Grid columns={3} gap={12}>
            <Stack gap={6}>
              <Text weight="semibold" style={{ color: theme.accent.primary }}>
                Node
              </Text>
              <Text size="small" tone="secondary">
                Cell · word · course node
              </Text>
            </Stack>
            <Stack gap={6}>
              <Text weight="semibold" style={{ color: theme.accent.primary }}>
                Edge
              </Text>
              <Text size="small" tone="secondary">
                Up/down/left/right · or 1-letter change
              </Text>
            </Stack>
            <Stack gap={6}>
              <Text weight="semibold" style={{ color: theme.accent.primary }}>
                Visit once
              </Text>
              <Text size="small" tone="secondary">
                Mark visited / rot / remove from dict
              </Text>
            </Stack>
          </Grid>
          <Divider />
          <Table
            headers={["Question you care about", "Tool", "Problem"]}
            rows={[
              [
                "How many separate groups?",
                "DFS / BFS count components",
                "Number of Islands",
              ],
              [
                "How long until everything is reached?",
                "Multi-source BFS by layers",
                "Rotten Oranges",
              ],
              [
                "Shortest path from A to B?",
                "BFS (unweighted edges)",
                "Word Ladder",
              ],
              [
                "Capture regions that cannot escape?",
                "Flood from borders first",
                "Surrounded Regions",
              ],
              [
                "Does a directed graph have a cycle?",
                "DFS 3-color or Kahn BFS",
                "Course Schedule",
              ],
            ]}
          />
        </Stack>
      </CardBody>
    </Card>
  );
}

function ForeverMnemonic() {
  const theme = useHostTheme();
  return (
    <Card>
      <CardHeader>The 10-second recall drill</CardHeader>
      <CardBody>
        <Stack gap={14}>
          <Grid columns={3} gap={12}>
            <Stack
              gap={8}
              style={{
                padding: 12,
                background: theme.fill.tertiary,
                borderRadius: 6,
              }}
            >
              <Text weight="semibold">ISLANDS</Text>
              <Text size="small">
                Find land → paint whole island → count paints.
              </Text>
              <Pill size="sm">count components</Pill>
            </Stack>
            <Stack
              gap={8}
              style={{
                padding: 12,
                background: theme.fill.tertiary,
                borderRadius: 6,
              }}
            >
              <Text weight="semibold">ORANGES</Text>
              <Text size="small">
                Every rotten starts fire → one ring per minute.
              </Text>
              <Pill size="sm">multi-source BFS</Pill>
            </Stack>
            <Stack
              gap={8}
              style={{
                padding: 12,
                background: theme.fill.tertiary,
                borderRadius: 6,
              }}
            >
              <Text weight="semibold">WORD LADDER</Text>
              <Text size="small">
                Words are rooms, one letter is a door → shortest walk.
              </Text>
              <Pill size="sm">shortest path BFS</Pill>
            </Stack>
            <Stack
              gap={8}
              style={{
                padding: 12,
                background: theme.fill.tertiary,
                borderRadius: 6,
              }}
            >
              <Text weight="semibold">SURROUNDED</Text>
              <Text size="small">
                Border O is safe → flood mark safe → flip leftover O to X.
              </Text>
              <Pill size="sm">border flood</Pill>
            </Stack>
            <Stack
              gap={8}
              style={{
                padding: 12,
                background: theme.fill.tertiary,
                borderRadius: 6,
              }}
            >
              <Text weight="semibold">CYCLE (DIRECTED)</Text>
              <Text size="small">
                Gray node again = back-edge = cycle. Or Kahn: leftover nodes.
              </Text>
              <Pill size="sm">DFS colors / Kahn</Pill>
            </Stack>
          </Grid>
        </Stack>
      </CardBody>
    </Card>
  );
}

function IslandsWalk() {
  const [step, setStep] = useCanvasState("island-step", 0);
  const frames: { title: string; grid: number[][]; count: number; tip: string }[] = [
    {
      title: "Scan left→right, top→bottom",
      grid: ISLAND_GRID,
      count: 0,
      tip: "Every land cell (1) you haven't visited yet is a NEW island.",
    },
    {
      title: "Hit land at (0,0) → island #1",
      grid: ISLAND_GRID,
      count: 1,
      tip: "Don't count neighbors separately — flood/paint the whole connected land first.",
    },
    {
      title: "Flood-fill island #1 (DFS/BFS)",
      grid: [
        [9, 9, 0, 0, 0],
        [9, 9, 0, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 0, 1, 1],
      ],
      count: 1,
      tip: "Mark visited so you never recount the same land. Water (0) is a wall.",
    },
    {
      title: "Next unvisited land (2,2) → island #2",
      grid: [
        [9, 9, 0, 0, 0],
        [9, 9, 0, 0, 0],
        [0, 0, 9, 0, 0],
        [0, 0, 0, 1, 1],
      ],
      count: 2,
      tip: "(2,2) touches (3,3) only on a DIAGONAL — diagonals do NOT count.",
    },
    {
      title: "Next unvisited land (3,3) → island #3",
      grid: [
        [9, 9, 0, 0, 0],
        [9, 9, 0, 0, 0],
        [0, 0, 9, 0, 0],
        [0, 0, 0, 9, 9],
      ],
      count: 3,
      tip: "(3,3) and (3,4) share an edge → same island. Answer = 3.",
    },
  ];
  const frame = frames[Math.min(step, frames.length - 1)];

  return (
    <Stack gap={16}>
      <Callout tone="warning" title="Rule that trips everyone: 4 directions only">
        Connected means share an EDGE — up, down, left, right. Touching only at
        a corner (diagonal) is NOT connected.
      </Callout>
      <Row gap={24} align="start">
        <Stack gap={12} style={{ minWidth: 220 }}>
          <MiniGrid grid={frame.grid} kind="island" />
        </Stack>
        <Stack gap={10} style={{ flex: 1 }}>
          <H3>{frame.title}</H3>
          <Stat value={String(frame.count)} label="Islands found so far" />
          <Text>{frame.tip}</Text>
          <Row gap={8}>
            <Button
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Prev
            </Button>
            <Button
              variant="primary"
              onClick={() => setStep((s) => Math.min(frames.length - 1, s + 1))}
              disabled={step >= frames.length - 1}
            >
              Next step
            </Button>
            <Button onClick={() => setStep(0)}>Reset</Button>
          </Row>
        </Stack>
      </Row>
    </Stack>
  );
}

function IslandsSolution() {
  return (
    <Stack gap={16}>
      <Callout tone="warning" title="Prefer iterative for large grids">
        Recursive DFS can hit StackOverflowError on a huge connected island
        (JVM call-stack limit). Use BFS (Queue) or iterative DFS (Stack) —
        heap memory instead of call stack.
      </Callout>

      <Callout tone="info" title="Idea">
        Scan every cell. When you find unvisited land, that starts a new
        island — increment the counter, then flood-fill (BFS/DFS) mark the
        entire connected component so you never recount it.
      </Callout>

      <Card>
        <CardHeader>Complexity</CardHeader>
        <CardBody>
          <ComplexityBadge
            time="O(R · C)"
            space="O(R · C) queue/stack (heap)"
          />
          <Text size="small" tone="secondary">
            Each cell enqueued/pushed at most once. Recursive DFS is also
            O(R · C) time but uses call-stack space (overflow risk).
          </Text>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Java — iterative BFS (recommended)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    private static final int[][] DIRS = {{1,0},{-1,0},{0,1},{0,-1}};

    public int numIslands(char[][] grid) {
        if (grid == null || grid.length == 0) return 0;
        int rows = grid.length, cols = grid[0].length;
        int islands = 0;

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (grid[r][c] != '1') continue;
                islands++;
                // Flood this island with a queue (no recursion)
                Queue<int[]> q = new ArrayDeque<>();
                q.offer(new int[]{r, c});
                grid[r][c] = '0';
                while (!q.isEmpty()) {
                    int[] cur = q.poll();
                    for (int[] d : DIRS) {
                        int nr = cur[0] + d[0], nc = cur[1] + d[1];
                        if (nr < 0 || nc < 0 || nr >= rows || nc >= cols
                                || grid[nr][nc] != '1') continue;
                        grid[nr][nc] = '0';
                        q.offer(new int[]{nr, nc});
                    }
                }
            }
        }
        return islands;
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Java — iterative DFS (Stack)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    private static final int[][] DIRS = {{1,0},{-1,0},{0,1},{0,-1}};

    public int numIslands(char[][] grid) {
        if (grid == null || grid.length == 0) return 0;
        int rows = grid.length, cols = grid[0].length;
        int islands = 0;

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (grid[r][c] != '1') continue;
                islands++;
                Deque<int[]> stack = new ArrayDeque<>();
                stack.push(new int[]{r, c});
                grid[r][c] = '0';
                while (!stack.isEmpty()) {
                    int[] cur = stack.pop();
                    for (int[] d : DIRS) {
                        int nr = cur[0] + d[0], nc = cur[1] + d[1];
                        if (nr < 0 || nc < 0 || nr >= rows || nc >= cols
                                || grid[nr][nc] != '1') continue;
                        grid[nr][nc] = '0';
                        stack.push(new int[]{nr, nc});
                    }
                }
            }
        }
        return islands;
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Why iterative works</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>
              1. <Code>islands++</Code> only when you discover fresh land —
              count of components.
            </Text>
            <Text>
              2. Mark visited immediately when you enqueue/push (
              <Code>'1' → '0'</Code>) so a cell is never added twice.
            </Text>
            <Text>
              3. <Code>Queue</Code> = BFS, <Code>Deque</Code> as stack = DFS.
              Same answer; only visit order differs.
            </Text>
            <Text>
              4. Time <Code>O(R·C)</Code>. Extra space <Code>O(R·C)</Code> on
              the heap — safe for large islands (no JVM call-stack overflow).
            </Text>
          </Stack>
        </CardBody>
      </Card>

      <CollapsibleSection title="Recursive DFS (small grids only)" defaultOpen={false}>
        <Stack gap={8}>
          <Text size="small" tone="secondary">
            Fine for interview demos / small inputs. Risk of StackOverflowError
            when one island spans tens of thousands of cells.
          </Text>
          <CodeBlock>{`class Solution {
    public int numIslands(char[][] grid) {
        if (grid == null || grid.length == 0) return 0;
        int rows = grid.length, cols = grid[0].length;
        int islands = 0;

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (grid[r][c] == '1') {
                    islands++;
                    dfs(grid, r, c);    // must pass cell (r,c), not sizes
                }
            }
        }
        return islands;
    }

    private void dfs(char[][] grid, int r, int c) {
        int rows = grid.length, cols = grid[0].length;
        if (r < 0 || c < 0 || r >= rows || c >= cols || grid[r][c] != '1') {
            return;
        }
        grid[r][c] = '0';
        dfs(grid, r + 1, c);
        dfs(grid, r - 1, c);
        dfs(grid, r, c + 1);
        dfs(grid, r, c - 1);
    }
}`}
          </CodeBlock>
        </Stack>
      </CollapsibleSection>
    </Stack>
  );
}

function OrangesWalk() {
  const [step, setStep] = useCanvasState("orange-step", 0);
  const frame = ORANGE_STEPS[Math.min(step, ORANGE_STEPS.length - 1)];

  return (
    <Stack gap={16}>
      <Callout tone="info" title="Memory hook: Infection by the minute">
        All rotten oranges infect at the same time. Put EVERY rotten orange in
        the queue first. Each BFS layer = 1 minute.
      </Callout>
      <Row gap={24} align="start">
        <Stack gap={12} style={{ minWidth: 160 }}>
          <MiniGrid grid={frame.grid} kind="orange" />
        </Stack>
        <Stack gap={10} style={{ flex: 1 }}>
          <H3>Minute {frame.minute}</H3>
          <Stat
            value={String(frame.minute)}
            label="Minutes elapsed"
            tone={step === ORANGE_STEPS.length - 1 ? "success" : "info"}
          />
          <Text>{frame.note}</Text>
          <Row gap={8}>
            <Button
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Prev
            </Button>
            <Button
              variant="primary"
              onClick={() =>
                setStep((s) => Math.min(ORANGE_STEPS.length - 1, s + 1))
              }
              disabled={step >= ORANGE_STEPS.length - 1}
            >
              Next minute
            </Button>
            <Button onClick={() => setStep(0)}>Reset</Button>
          </Row>
        </Stack>
      </Row>
    </Stack>
  );
}

function OrangesSolution() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Idea">
        Multi-source BFS. Seed the queue with all rotten cells at minute 0.
        Process the queue level-by-level; each level infects one ring of fresh
        neighbors. If any fresh remain when the queue dies, return -1.
      </Callout>

      <Card>
        <CardHeader>Complexity</CardHeader>
        <CardBody>
          <ComplexityBadge time="O(R · C)" space="O(R · C) queue" />
          <Text size="small" tone="secondary">
            Every cell processed at most once. Multi-source BFS layers = minutes.
          </Text>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Java solution (multi-source BFS)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    public int orangesRotting(int[][] grid) {
        int rows = grid.length, cols = grid[0].length;
        Queue<int[]> q = new ArrayDeque<>();
        int fresh = 0;

        // 1) Seed: every rotten orange starts the fire together
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (grid[r][c] == 2) {
                    q.offer(new int[]{r, c});
                } else if (grid[r][c] == 1) {
                    fresh++;
                }
            }
        }

        if (fresh == 0) return 0;     // nothing to rot

        int minutes = 0;
        int[][] dirs = {{1,0},{-1,0},{0,1},{0,-1}};

        // 2) BFS by layers — one layer = one minute
        while (!q.isEmpty() && fresh > 0) {
            int size = q.size();      // freeze current layer
            for (int i = 0; i < size; i++) {
                int[] cur = q.poll();
                for (int[] d : dirs) {
                    int nr = cur[0] + d[0], nc = cur[1] + d[1];
                    if (nr >= 0 && nc >= 0 && nr < rows && nc < cols
                            && grid[nr][nc] == 1) {
                        grid[nr][nc] = 2;  // become rotten
                        fresh--;
                        q.offer(new int[]{nr, nc});
                    }
                }
            }
            minutes++;
        }

        return fresh == 0 ? minutes : -1;
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Why this works — line by line</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>
              1. Seed ALL <Code>2</Code>s first — that is what makes it
              multi-source (simultaneous infection).
            </Text>
            <Text>
              2. <Code>int size = q.size()</Code> freezes the current layer so
              newly rotten oranges wait for the next minute.
            </Text>
            <Text>
              3. <Code>minutes++</Code> after each full layer — that is the
              answer clock.
            </Text>
            <Text>
              4. DFS is wrong here: infection is simultaneous across the whole
              frontier, not depth-first wander.
            </Text>
            <Text>
              5. Time <Code>O(R·C)</Code>, Space <Code>O(R·C)</Code> for the
              queue.
            </Text>
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}

function LadderWalk() {
  const theme = useHostTheme();
  const [step, setStep] = useCanvasState("ladder-step", 0);
  const visible = LADDER_PATH.slice(0, step + 1);

  return (
    <Stack gap={16}>
      <Callout tone="info" title="Memory hook: Rooms connected by one letter">
        Each word is a room. Differ by exactly one letter → edge. Shortest walk
        from begin to end = BFS.
      </Callout>
      <Row gap={24} align="start">
        <Stack gap={8} style={{ minWidth: 200 }}>
          {LADDER_PATH.map((node, i) => {
            const active = i <= step;
            return (
              <div
                key={node.word}
                style={{ display: "flex", gap: 10, alignItems: "center" }}
              >
                <div
                  style={{
                    width: 64,
                    padding: "8px 0",
                    textAlign: "center",
                    borderRadius: 4,
                    background: active
                      ? theme.accent.primary
                      : theme.fill.tertiary,
                    color: active
                      ? theme.text.onAccent
                      : theme.text.tertiary,
                    fontWeight: 700,
                    fontFamily: "monospace",
                    letterSpacing: 1,
                  }}
                >
                  {node.word}
                </div>
                <Text size="small" tone={active ? "secondary" : "tertiary"}>
                  {node.change}
                </Text>
              </div>
            );
          })}
        </Stack>
        <Stack gap={10} style={{ flex: 1 }}>
          <H3>
            Path length: {visible.length}
            {step === LADDER_PATH.length - 1 ? " (answer)" : ""}
          </H3>
          <Stat
            value={String(visible.length)}
            label="Words in ladder"
            tone={step === LADDER_PATH.length - 1 ? "success" : "info"}
          />
          <Text>
            beginWord = <Code>hit</Code>, endWord = <Code>cog</Code>. Shortest
            ladder length = <Text weight="semibold">5</Text>.
          </Text>
          <Row gap={8}>
            <Button
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Prev
            </Button>
            <Button
              variant="primary"
              onClick={() =>
                setStep((s) => Math.min(LADDER_PATH.length - 1, s + 1))
              }
              disabled={step >= LADDER_PATH.length - 1}
            >
              Next hop
            </Button>
            <Button onClick={() => setStep(0)}>Reset</Button>
          </Row>
        </Stack>
      </Row>
    </Stack>
  );
}

function LadderSolution() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Idea">
        Implicit graph: nodes = words, edges = one-letter difference. BFS from
        beginWord gives the shortest ladder length. Remove a word from the set
        when enqueued so each word is visited once.
      </Callout>

      <Card>
        <CardHeader>Complexity</CardHeader>
        <CardBody>
          <ComplexityBadge
            time="O(N · L · 26)"
            space="O(N) word set + queue"
          />
          <Text size="small" tone="secondary">
            N = dictionary size, L = word length. Each word mutated L×26 times;
            each word enqueued at most once.
          </Text>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Java solution (BFS)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.List;
import java.util.Queue;
import java.util.Set;

class Solution {
    public int ladderLength(String beginWord, String endWord,
                            List<String> wordList) {
        Set<String> words = new HashSet<>(wordList);
        if (!words.contains(endWord)) return 0;

        Queue<String> q = new ArrayDeque<>();
        q.offer(beginWord);
        int steps = 1;                    // ladder length includes beginWord

        while (!q.isEmpty()) {
            int size = q.size();
            for (int s = 0; s < size; s++) {
                String word = q.poll();
                if (word.equals(endWord)) return steps;

                char[] chars = word.toCharArray();
                for (int i = 0; i < chars.length; i++) {
                    char original = chars[i];
                    for (char ch = 'a'; ch <= 'z'; ch++) {
                        if (ch == original) continue;
                        chars[i] = ch;
                        String nxt = new String(chars);
                        if (words.contains(nxt)) {
                            words.remove(nxt);    // visit once
                            q.offer(nxt);
                        }
                    }
                    chars[i] = original;          // restore
                }
            }
            steps++;
        }
        return 0;                         // unreachable
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Why this works — line by line</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>
              1. <Code>HashSet</Code> from the word list gives O(1) neighbor
              checks.
            </Text>
            <Text>
              2. From each word, generate neighbors by changing one char —
              that is the edge definition (like 4-dirs on a grid).
            </Text>
            <Text>
              3. <Code>words.remove(nxt)</Code> = mark visited. Prevents
              re-enqueue and infinite loops.
            </Text>
            <Text>
              4. First time you reach <Code>endWord</Code> is the shortest
              path — property of BFS on unweighted graphs.{" "}
              <Code>size = q.size()</Code> walks one BFS layer at a time.
            </Text>
            <Text>
              5. Time roughly <Code>O(N · L · 26)</Code> where N = dict size, L
              = word length. Space <Code>O(N)</Code>.
            </Text>
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}


function CharGrid({ board }: { board: string[][] }) {
  const theme = useHostTheme();
  return (
    <Stack gap={4}>
      {board.map((row, r) => (
        <div key={r} style={{ display: "flex", gap: 4 }}>
          {row.map((cell, c) => {
            let bg = theme.fill.tertiary;
            let fg = theme.text.tertiary;
            if (cell === "O") {
              bg = theme.fill.secondary;
              fg = theme.text.primary;
            } else if (cell === "S") {
              bg = theme.accent.primary;
              fg = theme.text.onAccent;
            } else if (cell === "X") {
              bg = theme.fill.tertiary;
              fg = theme.text.secondary;
            }
            return (
              <div key={`${r}-${c}`}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: bg,
                    color: fg,
                    fontSize: 13,
                    fontWeight: 700,
                    borderRadius: 4,
                    border: `1px solid ${theme.stroke.tertiary}`,
                  }}
                >
                  {cell}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </Stack>
  );
}

function SurroundedWalk() {
  const [step, setStep] = useCanvasState("surrounded-step", 0);
  const frames: { title: string; board: string[][]; tip: string }[] = [
    {
      title: "Start — O = region, X = wall",
      board: [
        ["X", "X", "X", "X"],
        ["X", "O", "O", "X"],
        ["X", "X", "O", "X"],
        ["X", "O", "X", "X"],
      ],
      tip: "Any O that can reach the border (through other O's) is SAFE. Interior trapped O's get captured.",
    },
    {
      title: "Flood from every border O → mark S (safe)",
      board: [
        ["X", "X", "X", "X"],
        ["X", "O", "O", "X"],
        ["X", "X", "O", "X"],
        ["X", "S", "X", "X"],
      ],
      tip: "Bottom-border O at (3,1) is safe. Mark it S and flood its connected O's (none more here).",
    },
    {
      title: "Interior O's stay O — they are surrounded",
      board: [
        ["X", "X", "X", "X"],
        ["X", "O", "O", "X"],
        ["X", "X", "O", "X"],
        ["X", "S", "X", "X"],
      ],
      tip: "The blob at (1,1)-(1,2)-(2,2) never touches a border → will be captured.",
    },
    {
      title: "Flip leftover O → X; restore S → O",
      board: [
        ["X", "X", "X", "X"],
        ["X", "X", "X", "X"],
        ["X", "X", "X", "X"],
        ["X", "O", "X", "X"],
      ],
      tip: "Answer board: surrounded region captured; border-connected O survives.",
    },
  ];
  const frame = frames[Math.min(step, frames.length - 1)];

  return (
    <Stack gap={16}>
      <Callout tone="info" title="Memory hook: 'Save the border first'">
        Do NOT hunt interior regions. Start from borders, mark everything that
        can escape as safe, then capture whatever O is left.
      </Callout>
      <Row gap={24} align="start">
        <Stack gap={12} style={{ minWidth: 200 }}>
          <CharGrid board={frame.board} />
          <Row gap={8}>
            <Text size="small" tone="tertiary">O = open</Text>
            <Text size="small" tone="tertiary">S = safe</Text>
            <Text size="small" tone="tertiary">X = wall/captured</Text>
          </Row>
        </Stack>
        <Stack gap={10} style={{ flex: 1 }}>
          <H3>{frame.title}</H3>
          <Text>{frame.tip}</Text>
          <Row gap={8}>
            <Button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>Prev</Button>
            <Button variant="primary" onClick={() => setStep((s) => Math.min(frames.length - 1, s + 1))} disabled={step >= frames.length - 1}>Next step</Button>
            <Button onClick={() => setStep(0)}>Reset</Button>
          </Row>
        </Stack>
      </Row>
    </Stack>
  );
}

function SurroundedSolution() {
  return (
    <Stack gap={16}>
      <Callout tone="warning" title="Prefer iterative flood on large boards">
        Border flood can be deep — use Queue/Stack. Recursive DFS is fine for demos.
      </Callout>
      <Card>
        <CardHeader>Complexity</CardHeader>
        <CardBody>
          <ComplexityBadge time="O(R · C)" space="O(R · C) queue/stack" />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Java — iterative BFS from borders (recommended)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.ArrayDeque;
import java.util.Queue;

class Solution {
    private static final int[][] DIRS = {{1,0},{-1,0},{0,1},{0,-1}};

    public void solve(char[][] board) {
        if (board == null || board.length == 0) return;
        int rows = board.length, cols = board[0].length;
        Queue<int[]> q = new ArrayDeque<>();

        // 1) Seed every border 'O'
        for (int r = 0; r < rows; r++) {
            if (board[r][0] == 'O') { board[r][0] = 'S'; q.offer(new int[]{r, 0}); }
            if (board[r][cols - 1] == 'O') {
                board[r][cols - 1] = 'S'; q.offer(new int[]{r, cols - 1});
            }
        }
        for (int c = 0; c < cols; c++) {
            if (board[0][c] == 'O') { board[0][c] = 'S'; q.offer(new int[]{0, c}); }
            if (board[rows - 1][c] == 'O') {
                board[rows - 1][c] = 'S'; q.offer(new int[]{rows - 1, c});
            }
        }

        // 2) Flood all border-connected O → S
        while (!q.isEmpty()) {
            int[] cur = q.poll();
            for (int[] d : DIRS) {
                int nr = cur[0] + d[0], nc = cur[1] + d[1];
                if (nr < 0 || nc < 0 || nr >= rows || nc >= cols
                        || board[nr][nc] != 'O') continue;
                board[nr][nc] = 'S';
                q.offer(new int[]{nr, nc});
            }
        }

        // 3) Capture leftover O; restore S
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (board[r][c] == 'O') board[r][c] = 'X';
                else if (board[r][c] == 'S') board[r][c] = 'O';
            }
        }
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Why this works</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>1. Border O can never be captured — they &quot;touch water outside&quot;.</Text>
            <Text>2. Flood from borders marks the entire escape-connected region as S.</Text>
            <Text>3. Remaining O are fully enclosed by X → flip to X.</Text>
            <Text>4. Restore S → O. Twin of Islands, but start from borders, not every cell.</Text>
          </Stack>
        </CardBody>
      </Card>
      <CollapsibleSection title="Recursive DFS variant" defaultOpen={false}>
        <CodeBlock>{`class Solution {
    private static final int[][] DIRS = {{0,1},{0,-1},{1,0},{-1,0}};
    public void solve(char[][] board) {
        if (board == null || board.length == 0) return;
        int rows = board.length, cols = board[0].length;
        for (int r = 0; r < rows; r++) {
            if (board[r][0] == 'O') dfs(board, r, 0);
            if (board[r][cols - 1] == 'O') dfs(board, r, cols - 1);
        }
        for (int c = 0; c < cols; c++) {
            if (board[0][c] == 'O') dfs(board, 0, c);
            if (board[rows - 1][c] == 'O') dfs(board, rows - 1, c);
        }
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++) {
                if (board[r][c] == 'O') board[r][c] = 'X';
                else if (board[r][c] == 'S') board[r][c] = 'O';
            }
    }
    private void dfs(char[][] board, int r, int c) {
        if (r < 0 || c < 0 || r >= board.length || c >= board[0].length
                || board[r][c] != 'O') return;
        board[r][c] = 'S';
        for (int[] d : DIRS) dfs(board, r + d[0], c + d[1]);
    }
}`}
        </CodeBlock>
      </CollapsibleSection>
    </Stack>
  );
}

function CycleWalk() {
  const [step, setStep] = useCanvasState("cycle-step", 0);
  const frames: { title: string; tip: string; detail: string; result: string }[] = [
    {
      title: "Directed graph = courses with prerequisites",
      tip: "Edge A → B means A must come before B (or: take A then B).",
      detail: "Example: 0 → 1 → 2 and also 2 → 1. Nodes: 0,1,2.",
      result: "Looking for a cycle…",
    },
    {
      title: "DFS 3-color: WHITE → GRAY → BLACK",
      tip: "WHITE = unvisited, GRAY = on current path, BLACK = done.",
      detail: "Visit 0 (GRAY) → 1 (GRAY) → 2 (GRAY). From 2 see edge to 1 which is GRAY.",
      result: "Back-edge to GRAY = CYCLE",
    },
    {
      title: "Kahn's BFS alternative",
      tip: "Start with indegree-0 nodes; peel the graph layer by layer.",
      detail: "If 1→2 and 2→1, both have indegree 1 — queue starts empty (or never finishes all).",
      result: "taken < numCourses → CYCLE",
    },
    {
      title: "No-cycle case",
      tip: "prerequisites = [[1,0]] only — edge 0 → 1.",
      detail: "DFS never sees a GRAY back-edge. Kahn: take 0 then 1, taken == 2.",
      result: "canFinish = true",
    },
  ];
  const frame = frames[Math.min(step, frames.length - 1)];

  return (
    <Stack gap={16}>
      <Callout tone="info" title="Memory hook: 'Gray again = cycle'">
        In a directed graph, revisiting a node that is still on your current DFS
        path (GRAY) means a back-edge — a cycle. Kahn: if you cannot take all
        nodes, leftovers are in a cycle.
      </Callout>
      <Stack gap={10}>
        <H3>{frame.title}</H3>
        <Stat value={frame.result} label="Status" tone={step === 1 || step === 2 ? "warning" : "info"} />
        <Text>{frame.tip}</Text>
        <Text size="small" tone="secondary">{frame.detail}</Text>
        <Row gap={8}>
          <Button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>Prev</Button>
          <Button variant="primary" onClick={() => setStep((s) => Math.min(frames.length - 1, s + 1))} disabled={step >= frames.length - 1}>Next step</Button>
          <Button onClick={() => setStep(0)}>Reset</Button>
        </Row>
      </Stack>
    </Stack>
  );
}

function CycleSolution() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Two interview-ready approaches">
        DFS 3-color detects a back-edge. Kahn&apos;s BFS (topological) fails to
        consume all nodes if a cycle exists. Both are O(V+E).
      </Callout>
      <Card>
        <CardHeader>Complexity</CardHeader>
        <CardBody>
          <ComplexityBadge time="O(V + E)" space="O(V + E)" />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Java — DFS 3-color (cycle detection)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.*;

class Solution {
    // 0 = WHITE, 1 = GRAY (on path), 2 = BLACK (done)
    public boolean canFinish(int numCourses, int[][] prerequisites) {
        List<List<Integer>> graph = new ArrayList<>();
        for (int i = 0; i < numCourses; i++) graph.add(new ArrayList<>());
        for (int[] p : prerequisites) graph.get(p[1]).add(p[0]); // p[1] → p[0]

        int[] color = new int[numCourses];
        for (int i = 0; i < numCourses; i++) {
            if (color[i] == 0 && hasCycle(graph, color, i)) return false;
        }
        return true; // no cycle → can finish
    }

    private boolean hasCycle(List<List<Integer>> g, int[] color, int node) {
        color[node] = 1; // GRAY — entering path
        for (int next : g.get(node)) {
            if (color[next] == 1) return true;          // back-edge
            if (color[next] == 0 && hasCycle(g, color, next)) return true;
        }
        color[node] = 2; // BLACK — done
        return false;
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Java — Kahn&apos;s BFS (topological)</CardHeader>
        <CardBody>
          <CodeBlock>{`import java.util.*;

class Solution {
    public boolean canFinish(int numCourses, int[][] prerequisites) {
        List<List<Integer>> graph = new ArrayList<>();
        int[] indegree = new int[numCourses];
        for (int i = 0; i < numCourses; i++) graph.add(new ArrayList<>());
        for (int[] p : prerequisites) {
            graph.get(p[1]).add(p[0]);
            indegree[p[0]]++;
        }
        Queue<Integer> q = new ArrayDeque<>();
        for (int i = 0; i < numCourses; i++)
            if (indegree[i] == 0) q.offer(i);

        int taken = 0;
        while (!q.isEmpty()) {
            int course = q.poll();
            taken++;
            for (int next : graph.get(course)) {
                if (--indegree[next] == 0) q.offer(next);
            }
        }
        return taken == numCourses; // false ⇒ cycle
    }
}`}
          </CodeBlock>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Why this works</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>1. GRAY means &quot;still on my recursion stack&quot; — seeing it again is a cycle.</Text>
            <Text>2. BLACK means fully explored — safe to ignore.</Text>
            <Text>3. Kahn peels indegree-0 nodes; a cycle has no indegree-0 entry → leftovers.</Text>
            <Text>4. Same problem family as Alien Dictionary / Course Schedule II.</Text>
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}


function Comparison() {
  return (
    <Card>
      <CardHeader>Side-by-side so they stop confusing you</CardHeader>
      <CardBody>
        <Table
          headers={["", "Islands", "Oranges", "Ladder", "Surrounded", "Cycle"]}
          rows={[
            [
              "Looks like",
              "grid land/water",
              "grid oranges",
              "word graph",
              "grid O/X",
              "directed edges",
            ],
            [
              "Start from",
              "each unvisited land",
              "all rotten",
              "beginWord",
              "all border O",
              "each WHITE / indegree 0",
            ],
            [
              "Goal",
              "count components",
              "minutes to infect",
              "shortest path",
              "capture trapped O",
              "detect cycle",
            ],
            [
              "Tool",
              "DFS/BFS flood",
              "multi-source BFS",
              "BFS",
              "border flood",
              "DFS colors / Kahn",
            ],
            [
              "Cycle signal",
              "—",
              "—",
              "—",
              "—",
              "GRAY again / leftovers",
            ],
          ]}
          rowTone={[undefined, undefined, "info", undefined, undefined]}
        />
      </CardBody>
    </Card>
  );
}


function CoreProblemStatement({ problem }: { problem: Problem }) {
  const data: Record<
    Problem,
    {
      title: string;
      lc: string;
      difficulty: string;
      statement: string;
      input: string;
      output: string;
      examples: { title: string; input: string; output: string; note?: string }[];
      constraints: string[];
      ask: string;
    }
  > = {
    islands: {
      title: "Number of Islands",
      lc: "LC 200",
      difficulty: "Medium",
      statement:
        "Given an m × n 2D binary grid which represents a map of '1' (land) and '0' (water), return the number of islands. An island is surrounded by water and is formed by connecting adjacent lands horizontally or vertically (4 directions). You may assume all four edges of the grid are surrounded by water.",
      input: "char[][] grid",
      output: "int — number of islands",
      examples: [
        {
          title: "Example 1",
          input:
            'grid = [["1","1","1","1","0"],["1","1","0","1","0"],["1","1","0","0","0"],["0","0","0","0","0"]]',
          output: "1",
        },
        {
          title: "Example 2",
          input:
            'grid = [["1","1","0","0","0"],["1","1","0","0","0"],["0","0","1","0","0"],["0","0","0","1","1"]]',
          output: "3",
          note: "Diagonals do NOT connect. Three separate islands.",
        },
      ],
      constraints: [
        "m == grid.length, n == grid[i].length",
        "1 ≤ m, n ≤ 300",
        "grid[i][j] is '0' or '1'",
      ],
      ask: "How many separate land groups (connected components)?",
    },
    oranges: {
      title: "Rotting Oranges",
      lc: "LC 994",
      difficulty: "Medium",
      statement:
        "You are given an m × n grid where each cell can be 0 (empty), 1 (fresh orange), or 2 (rotten orange). Every minute, any fresh orange that is 4-directionally adjacent to a rotten orange becomes rotten. Return the minimum number of minutes that must elapse until no cell has a fresh orange. If this is impossible, return -1.",
      input: "int[][] grid",
      output: "int — minutes, or -1 if impossible",
      examples: [
        {
          title: "Example 1",
          input: "grid = [[2,1,1],[1,1,0],[0,1,1]]",
          output: "4",
        },
        {
          title: "Example 2",
          input: "grid = [[2,1,1],[0,1,1],[1,0,1]]",
          output: "-1",
          note: "Bottom-left fresh orange is unreachable.",
        },
        {
          title: "Example 3",
          input: "grid = [[0,2]]",
          output: "0",
          note: "No fresh oranges at start.",
        },
      ],
      constraints: [
        "m == grid.length, n == grid[i].length",
        "1 ≤ m, n ≤ 10",
        "grid[i][j] is 0, 1, or 2",
      ],
      ask: "How long until everything is infected? (multi-source BFS)",
    },
    ladder: {
      title: "Word Ladder",
      lc: "LC 127",
      difficulty: "Hard",
      statement:
        "A transformation sequence from beginWord to endWord using a dictionary wordList is a sequence beginWord → s1 → s2 → … → sk such that every adjacent pair differs by exactly one letter, every si (i ≥ 1) is in wordList, and sk == endWord. Given beginWord, endWord, and wordList, return the number of words in the shortest transformation sequence, or 0 if no such sequence exists.",
      input: "String beginWord, String endWord, List<String> wordList",
      output: "int — ladder length (words in path), or 0",
      examples: [
        {
          title: "Example 1",
          input:
            'beginWord = "hit", endWord = "cog", wordList = ["hot","dot","dog","lot","log","cog"]',
          output: "5",
          note: "One shortest ladder: hit → hot → dot → dog → cog",
        },
        {
          title: "Example 2",
          input:
            'beginWord = "hit", endWord = "cog", wordList = ["hot","dot","dog","lot","log"]',
          output: "0",
          note: "endWord not in dictionary → impossible.",
        },
      ],
      constraints: [
        "1 ≤ beginWord.length ≤ 10",
        "endWord.length == beginWord.length",
        "1 ≤ wordList.length ≤ 5000",
        "All words have the same length; consist of lowercase letters",
      ],
      ask: "Shortest path in an unweighted word graph?",
    },
    surrounded: {
      title: "Surrounded Regions",
      lc: "LC 130",
      difficulty: "Medium",
      statement:
        "Given an m × n matrix board containing 'X' and 'O', capture all regions that are 4-directionally surrounded by 'X'. A region is captured by flipping all 'O's into 'X's in that surrounded region. Any 'O' on the border (or connected to a border 'O') cannot be captured.",
      input: "char[][] board (modified in-place)",
      output: "void — board updated in place",
      examples: [
        {
          title: "Example 1",
          input:
            'board = [["X","X","X","X"],["X","O","O","X"],["X","X","O","X"],["X","O","X","X"]]',
          output:
            '[["X","X","X","X"],["X","X","X","X"],["X","X","X","X"],["X","O","X","X"]]',
          note: "Interior O-region is captured; bottom-border O survives.",
        },
        {
          title: "Example 2",
          input: 'board = [["X"]]',
          output: '[["X"]]',
        },
      ],
      constraints: [
        "m == board.length, n == board[i].length",
        "1 ≤ m, n ≤ 200",
        "board[i][j] is 'X' or 'O'",
      ],
      ask: "Which O regions cannot escape to the border?",
    },
    cycle: {
      title: "Course Schedule (Cycle in Directed Graph)",
      lc: "LC 207",
      difficulty: "Medium",
      statement:
        "There are numCourses courses labeled from 0 to numCourses - 1. You are given an array prerequisites where prerequisites[i] = [ai, bi] means you must take course bi before course ai (edge bi → ai). Return true if you can finish all courses. Otherwise return false. You cannot finish if the prerequisite graph contains a cycle.",
      input: "int numCourses, int[][] prerequisites",
      output: "boolean — true if no cycle (can finish)",
      examples: [
        {
          title: "Example 1",
          input: "numCourses = 2, prerequisites = [[1,0]]",
          output: "true",
          note: "Take 0 then 1.",
        },
        {
          title: "Example 2",
          input: "numCourses = 2, prerequisites = [[1,0],[0,1]]",
          output: "false",
          note: "0 ⇄ 1 cycle.",
        },
      ],
      constraints: [
        "1 ≤ numCourses ≤ 2000",
        "0 ≤ prerequisites.length ≤ 5000",
        "prerequisites[i].length == 2",
        "0 ≤ ai, bi < numCourses; ai ≠ bi",
      ],
      ask: "Does this directed graph have a cycle?",
    },
  };

  const p = data[problem];

  return (
    <Stack gap={16}>
      <Row gap={8} wrap align="center">
        <Pill size="sm">{p.lc}</Pill>
        <Pill size="sm">{p.difficulty}</Pill>
      </Row>
      <Text weight="semibold">{p.statement}</Text>
      <Callout tone="info" title="What you are really being asked">
        {p.ask}
      </Callout>
      <Grid columns={2} gap={12}>
        <Stack gap={4}>
          <Text size="small" tone="tertiary">
            Input
          </Text>
          <Code>{p.input}</Code>
        </Stack>
        <Stack gap={4}>
          <Text size="small" tone="tertiary">
            Output
          </Text>
          <Code>{p.output}</Code>
        </Stack>
      </Grid>
      <Divider />
      <Text weight="semibold">Examples</Text>
      {p.examples.map((ex) => (
        <div key={ex.title}>
          <Card>
            <CardHeader>{ex.title}</CardHeader>
            <CardBody>
              <Stack gap={8}>
                <Text size="small">
                  <Text weight="semibold">Input: </Text>
                  {ex.input}
                </Text>
                <Text size="small">
                  <Text weight="semibold">Output: </Text>
                  {ex.output}
                </Text>
                {ex.note ? (
                  <Text size="small" tone="secondary">
                    {ex.note}
                  </Text>
                ) : null}
              </Stack>
            </CardBody>
          </Card>
        </div>
      ))}
      <Divider />
      <Text weight="semibold">Constraints</Text>
      <Stack gap={4}>
        {p.constraints.map((c) => (
          <div key={c}>
            <Text size="small" tone="secondary">
              • {c}
            </Text>
          </div>
        ))}
      </Stack>
    </Stack>
  );
}


function OfflineDownload() {
  const htmlPath = "/Users/mohdnadeem/Documents/Codex/2026-08-02/python3-c-dquote-from-huggingface-hub/outputs/stock-analyzer-starter/study-guides/graph-bfs-faang-study-guide.html";
  const fileUrl = "file:///Users/mohdnadeem/Documents/Codex/2026-08-02/python3-c-dquote-from-huggingface-hub/outputs/stock-analyzer-starter/study-guides/graph-bfs-faang-study-guide.html";

  const openGuide = () => {
    const w = typeof globalThis !== "undefined" ? (globalThis as { open?: (url: string) => void }).open : undefined;
    if (w) w(fileUrl);
  };

  return (
    <Card>
      <CardHeader trailing={<Pill size="sm">Offline</Pill>}>
        Download / view later
      </CardHeader>
      <CardBody>
        <Stack gap={12}>
          <Text>
            This canvas stays in Cursor. For phone, print, or anytime offline,
            use the self-contained HTML study guide (all 5 core + 16 FAANG Java
            solutions).
          </Text>
          <Row gap={8} wrap>
            <Button variant="primary" onClick={openGuide}>
              Open offline guide
            </Button>
            <Link href={fileUrl}>Open HTML in browser</Link>
          </Row>
          <Text size="small" tone="tertiary">
            Path: {htmlPath}
          </Text>
          <Text size="small" tone="secondary">
            Tip: open the HTML, then use File → Save Page As… to keep a copy on
            Desktop, Drive, or USB.
          </Text>
        </Stack>
      </CardBody>
    </Card>
  );
}

function FaangBank() {
  const [company, setCompany] = useCanvasState<Company>("company", "all");
  const [pattern, setPattern] = useCanvasState<string>("faang-pattern", "all");
  const [selected, setSelected] = useCanvasState<string>(
    "faang-selected",
    "Max Area of Island",
  );

  const filtered = FAANG_PROBLEMS.filter((p) => {
    const companyOk = company === "all" || p.companies.includes(company);
    const patternOk = pattern === "all" || p.pattern === pattern;
    return companyOk && patternOk;
  });

  const patterns = [
    "all",
    "count components",
    "multi-source BFS",
    "shortest path BFS",
    "DFS backtrack",
    "graph BFS/DFS",
  ];

  const active =
    filtered.find((p) => p.name === selected) ?? filtered[0] ?? FAANG_PROBLEMS[0];
  const sol = FAANG_SOLUTIONS[active.name];

  return (
    <Stack gap={16}>
      <Stack gap={8}>
        <H2>Same-family FAANG problems — all 16 implemented</H2>
        <Text tone="secondary">
          Filter, pick a problem, read the Java solution. Every one maps back to
          Islands, Oranges, or Word Ladder.
        </Text>
      </Stack>

      <Row gap={8} wrap>
        <Text size="small" tone="tertiary" style={{ alignSelf: "center" }}>
          Company
        </Text>
        {(
          [
            ["all", "All"],
            ["amazon", "Amazon"],
            ["google", "Google"],
            ["microsoft", "Microsoft"],
          ] as const
        ).map(([id, label]) => (
          <div key={id}>
            <Button
              variant={company === id ? "primary" : "secondary"}
              onClick={() => setCompany(id)}
            >
              {label}
            </Button>
          </div>
        ))}
      </Row>

      <Row gap={8} wrap>
        <Text size="small" tone="tertiary" style={{ alignSelf: "center" }}>
          Pattern
        </Text>
        {patterns.map((p) => (
          <div key={p}>
            <Button
              variant={pattern === p ? "primary" : "ghost"}
              onClick={() => setPattern(p)}
            >
              {p === "all" ? "All patterns" : p}
            </Button>
          </div>
        ))}
      </Row>

      <Stat
        value={String(filtered.length)}
        label="Problems matching filters"
        tone="info"
      />

      <Row gap={8} wrap>
        {filtered.map((p) => (
          <div key={p.name}>
            <Button
              variant={active.name === p.name ? "primary" : "secondary"}
              onClick={() => setSelected(p.name)}
            >
              {p.lc.replace("LC ", "")} · {p.name}
            </Button>
          </div>
        ))}
      </Row>

      <Card>
        <CardHeader
          trailing={
            <Pill size="sm">
              twin: {active.like}
            </Pill>
          }
        >
          {active.name} ({active.lc})
        </CardHeader>
        <CardBody>
          <Stack gap={14}>
            <Text>{active.why}</Text>
            <Text size="small" tone="secondary">
              Companies:{" "}
              {active.companies
                .map((c) => c[0].toUpperCase() + c.slice(1))
                .join(" · ")}
              {" · "}Hint: {active.hint}
            </Text>
            {sol?.iterative ? (
              <Stack gap={10}>
                <H3>Java — iterative (recommended)</H3>
                <CodeBlock>{sol.iterative}</CodeBlock>
                <CollapsibleSection title="Recursive variant (small inputs)" defaultOpen={false}>
                  <CodeBlock>{sol.code}</CodeBlock>
                </CollapsibleSection>
              </Stack>
            ) : (
              <Stack gap={10}>
                <H3>Java solution</H3>
                {sol ? (
                  <CodeBlock>{sol.code}</CodeBlock>
                ) : (
                  <Text tone="secondary">Solution missing for this title.</Text>
                )}
              </Stack>
            )}
            {sol && (
              <Stack gap={10}>
                <ComplexityBadge time={sol.time} space={sol.space} />
                <Text weight="semibold">Why it works</Text>
                {sol.bullets.map((b, i) => (
                  <div key={String(i)}>
                    <Text size="small">
                      {i + 1}. {b}
                    </Text>
                  </div>
                ))}
              </Stack>
            )}
          </Stack>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Interview attack plan</CardHeader>
        <CardBody>
          <Table
            headers={["You hear…", "Reach for…", "Starter problems"]}
            rows={[
              [
                "Count / size of connected groups",
                "Islands (DFS flood)",
                "Max Area, Provinces, Flood Fill, Keys & Rooms",
              ],
              [
                "Distance / time from many sources",
                "Oranges (multi-source BFS)",
                "01 Matrix, Walls & Gates, Pacific Atlantic, Shortest Bridge",
              ],
              [
                "Fewest steps in an unweighted graph",
                "Word Ladder (BFS)",
                "Open the Lock, Binary Matrix path, Knight Moves",
              ],
            ]}
          />
        </CardBody>
      </Card>
    </Stack>
  );
}


export default function GraphBfsTrioCanvas() {
  const [problem, setProblem] = useCanvasState<Problem>("problem", "islands");
  const [mode, setMode] = useCanvasState<PanelMode>("mode", "problem");

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 960 }}>
      <Stack gap={8}>
        <H1>Core Graph Patterns</H1>
        <Text tone="secondary">
          Five core patterns + full Java solutions + the FAANG remix bank.
        </Text>
      </Stack>

      <MasterKey />
      <ForeverMnemonic />

      <OfflineDownload />

      <Stack gap={12}>
        <H2>Core problems (5)</H2>
        <Row gap={8} wrap>
          <Button
            variant={problem === "islands" ? "primary" : "secondary"}
            onClick={() => setProblem("islands")}
          >
            1. Islands
          </Button>
          <Button
            variant={problem === "oranges" ? "primary" : "secondary"}
            onClick={() => setProblem("oranges")}
          >
            2. Oranges
          </Button>
          <Button
            variant={problem === "ladder" ? "primary" : "secondary"}
            onClick={() => setProblem("ladder")}
          >
            3. Word Ladder
          </Button>
          <Button
            variant={problem === "surrounded" ? "primary" : "secondary"}
            onClick={() => setProblem("surrounded")}
          >
            4. Surrounded Regions
          </Button>
          <Button
            variant={problem === "cycle" ? "primary" : "secondary"}
            onClick={() => setProblem("cycle")}
          >
            5. Cycle (Directed)
          </Button>
        </Row>

        <Row gap={8} wrap>
          <Button
            variant={mode === "problem" ? "primary" : "ghost"}
            onClick={() => setMode("problem")}
          >
            Problem
          </Button>
          <Button
            variant={mode === "walk" ? "primary" : "ghost"}
            onClick={() => setMode("walk")}
          >
            Walkthrough
          </Button>
          <Button
            variant={mode === "solution" ? "primary" : "ghost"}
            onClick={() => setMode("solution")}
          >
            Solution + explanation
          </Button>
        </Row>

        <Card>
          <CardHeader>
            {problem === "islands"
              ? "Number of Islands (LC 200)"
              : problem === "oranges"
                ? "Rotting Oranges (LC 994)"
                : problem === "ladder"
                  ? "Word Ladder (LC 127)"
                  : problem === "surrounded"
                    ? "Surrounded Regions (LC 130)"
                    : "Cycle Detection / Course Schedule (LC 207)"}
            {" · "}
            {mode === "problem"
              ? "Problem"
              : mode === "walk"
                ? "Walkthrough"
                : "Solution"}
          </CardHeader>
          <CardBody>
            {mode === "problem" ? (
              <CoreProblemStatement problem={problem} />
            ) : (
              <>
                {problem === "islands" &&
                  (mode === "walk" ? <IslandsWalk /> : <IslandsSolution />)}
                {problem === "oranges" &&
                  (mode === "walk" ? <OrangesWalk /> : <OrangesSolution />)}
                {problem === "ladder" &&
                  (mode === "walk" ? <LadderWalk /> : <LadderSolution />)}
                {problem === "surrounded" &&
                  (mode === "walk" ? (
                    <SurroundedWalk />
                  ) : (
                    <SurroundedSolution />
                  ))}
                {problem === "cycle" &&
                  (mode === "walk" ? <CycleWalk /> : <CycleSolution />)}
              </>
            )}
          </CardBody>
        </Card>
      </Stack>

      <Comparison />

      <Divider />

      <FaangBank />

      <Text size="small" tone="tertiary">
        Drill: recite the five one-liners, then pick one FAANG remix and name
        which twin it is before coding.
      </Text>
    </Stack>
  );
}
