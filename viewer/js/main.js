class HeightmapViewer {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.heightmapMesh = null;
        this.currentGridScale = 5; // 1 for 1m grid, 5 for 5m grid
        this.heightData = null;
        this.originalWidth = 0;
        this.originalHeight = 0;
        
        this.initializeScene();
        this.setupEventListeners();
    }

    initializeScene() {
        const canvas = document.getElementById('canvas');
        
        // Create scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x87CEEB);

        // Create camera with extended far plane
        this.camera = new THREE.PerspectiveCamera(
            75, 
            window.innerWidth / window.innerHeight, 
            0.1, 
            100000  // Extended far clipping plane
        );
        this.camera.position.set(0, 500, 500);

        // Create renderer
        this.renderer = new THREE.WebGLRenderer({ 
            canvas: canvas, 
            antialias: true 
        });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.shadowMap.enabled = false;
        // this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        // Add lights
        this.setupLighting();

        // Setup controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        // Initial limits, will be updated when terrain is loaded
        this.controls.maxDistance = 10000;
        this.controls.minDistance = 1;

        // Start render loop
        this.animate();

        // Handle window resize
        window.addEventListener('resize', () => this.onWindowResize());
    }

    setupLighting() {
        // Ambient light
        const ambientLight = new THREE.AmbientLight(0x404040, 0.3);
        this.scene.add(ambientLight);

        // Directional light (sun)
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(500, 1000, 300);
        directionalLight.castShadow = false;
        directionalLight.shadow.mapSize.width = 2048;
        directionalLight.shadow.mapSize.height = 2048;
        directionalLight.shadow.camera.near = 0.5;
        directionalLight.shadow.camera.far = 2000;
        directionalLight.shadow.camera.left = -1000;
        directionalLight.shadow.camera.right = 1000;
        directionalLight.shadow.camera.top = 1000;
        directionalLight.shadow.camera.bottom = -1000;
        this.scene.add(directionalLight);

        // Additional fill light
        const fillLight = new THREE.DirectionalLight(0x87CEEB, 0.2);
        fillLight.position.set(-500, 200, -500);
        this.scene.add(fillLight);
    }

    setupEventListeners() {
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const grid1mBtn = document.getElementById('grid1m');
        const grid5mBtn = document.getElementById('grid5m');
        const resetViewBtn = document.getElementById('resetView');

        // Drop zone events
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', this.handleDragOver.bind(this));
        dropZone.addEventListener('dragleave', this.handleDragLeave.bind(this));
        dropZone.addEventListener('drop', this.handleDrop.bind(this));

        // File input
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.loadEXRFile(e.target.files[0]);
            }
        });

        // Grid resolution buttons
        grid1mBtn.addEventListener('click', () => this.setGridScale(1));
        grid5mBtn.addEventListener('click', () => this.setGridScale(5));

        // Reset view button
        resetViewBtn.addEventListener('click', () => this.resetView());

        // Prevent default drag behaviors on document
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => e.preventDefault());
    }

    handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('dragover');
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
    }

    handleDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].name.toLowerCase().endsWith('.exr')) {
            this.loadEXRFile(files[0]);
        } else {
            alert('EXRファイルを選択してください。');
        }
    }

    showLoading(show = true) {
        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        
        if (show) {
            overlay.style.display = 'flex';
            loadingText.textContent = 'EXRファイルを読み込み中...';
        } else {
            overlay.style.display = 'none';
        }
    }

    async loadEXRFile(file) {
        this.showLoading(true);
        
        try {
            const arrayBuffer = await file.arrayBuffer();
            const loader = new THREE.EXRLoader();
            
            // Load EXR data
            const exrData = loader.parse(arrayBuffer);
            
            // Update loading text
            document.getElementById('loadingText').textContent = 'ハイトマップを生成中...';
            
            // Process height data
            this.processHeightData(exrData);
            
            // Generate mesh
            await this.generateHeightmapMesh();
            
            // Hide drop zone and show controls
            document.getElementById('dropZone').classList.add('hidden');
            document.getElementById('controls').style.display = 'block';
            document.getElementById('info').style.display = 'block';
            document.getElementById('terrainInfo').style.display = 'block';
            
            this.showLoading(false);
            
        } catch (error) {
            console.error('EXRファイルの読み込みに失敗しました:', error);
            alert('EXRファイルの読み込みに失敗しました。ファイル形式を確認してください。');
            this.showLoading(false);
        }
    }

    processHeightData(exrData) {
        const { data, width, height } = exrData;
        this.originalWidth = width;
        this.originalHeight = height;
        
        // Convert to height array (assuming single channel FLOAT data)
        // EXR data is typically in RGBA format, we'll use the R channel for height
        this.heightData = new Float32Array(width * height);
        
        for (let i = 0; i < width * height; i++) {
            // Extract height from red channel (assuming height data is in R channel)
            this.heightData[i] = data[i * 4]; // R channel
        }
        
        console.log(`Height data processed: ${width} x ${height}`);
    }

    async generateHeightmapMesh() {
        return new Promise((resolve) => {
            if (this.heightmapMesh) {
                this.scene.remove(this.heightmapMesh);
                // Properly dispose of geometry and material
                if (this.heightmapMesh.geometry) {
                    this.heightmapMesh.geometry.dispose();
                }
                if (this.heightmapMesh.material) {
                    this.heightmapMesh.material.dispose();
                }
                this.heightmapMesh = null;
            }

            // Calculate optimal mesh dimensions based on input resolution and grid scale
            const maxVertices = 2048; // Maximum vertices per dimension for performance
            const aspect = this.originalWidth / this.originalHeight;
            
            // Calculate mesh dimensions in vertices (grid points)
            let meshWidth, meshHeight;
            
            // Determine grid dimensions based on current grid scale and original resolution
            // Each pixel represents this.currentGridScale meters
            const terrainWidthMeters = this.originalWidth * this.currentGridScale;
            const terrainHeightMeters = this.originalHeight * this.currentGridScale;
            
            // Calculate vertices needed to maintain proper resolution
            // But limit to maxVertices for performance
            if (aspect >= 1) {
                meshWidth = Math.min(this.originalWidth, maxVertices);
                meshHeight = Math.min(Math.round(meshWidth / aspect), maxVertices);
            } else {
                meshHeight = Math.min(this.originalHeight, maxVertices);
                meshWidth = Math.min(Math.round(meshHeight * aspect), maxVertices);
            }
            
            // Ensure minimum resolution
            meshWidth = Math.max(meshWidth, 64);
            meshHeight = Math.max(meshHeight, 64);

            // Create geometry with actual terrain dimensions in meters
            const geometry = new THREE.PlaneGeometry(
                terrainWidthMeters,
                terrainHeightMeters,
                meshWidth - 1,
                meshHeight - 1
            );

            // Apply height displacement
            const vertices = geometry.attributes.position.array;
            const resampledHeights = this.resampleHeightData(meshWidth, meshHeight);

            for (let i = 0; i < meshWidth * meshHeight; i++) {
                const vertexIndex = i * 3;
                vertices[vertexIndex + 2] = resampledHeights[i]; // Z coordinate for height
            }

            geometry.attributes.position.needsUpdate = true;
            geometry.computeVertexNormals();
            
            // Remove UV coordinates to prevent texture conflicts
            geometry.deleteAttribute('uv');

            // Create material with height-based coloring
            const material = new THREE.MeshLambertMaterial({
                vertexColors: true,
                side: THREE.DoubleSide,
                wireframe: false,
                map: null,  // No texture map
                transparent: false
            });

            // Add vertex colors based on height
            this.addVertexColors(geometry, resampledHeights);

            // Rotate to make it horizontal (XZ plane)
            geometry.rotateX(-Math.PI / 2);

            // Create mesh
            this.heightmapMesh = new THREE.Mesh(geometry, material);
            this.heightmapMesh.receiveShadow = false;
            this.heightmapMesh.castShadow = false;
            
            this.scene.add(this.heightmapMesh);

            // Update camera position based on data bounds
            this.updateCameraPosition(resampledHeights);
            
            console.log(`Mesh generated: ${meshWidth}x${meshHeight} vertices, terrain: ${terrainWidthMeters}x${terrainHeightMeters}m, grid scale: ${this.currentGridScale}m`);

            resolve();
        });
    }

    resampleHeightData(targetWidth, targetHeight) {
        const resampled = new Float32Array(targetWidth * targetHeight);
        const scaleX = this.originalWidth / targetWidth;
        const scaleY = this.originalHeight / targetHeight;

        for (let y = 0; y < targetHeight; y++) {
            for (let x = 0; x < targetWidth; x++) {
                const srcX = Math.floor(x * scaleX);
                // Flip Y coordinate to correct north-south orientation
                const srcY = Math.floor((targetHeight - 1 - y) * scaleY);
                const srcIndex = (srcY * this.originalWidth + srcX);
                
                const targetIndex = y * targetWidth + x;
                resampled[targetIndex] = this.heightData[srcIndex] || 0;
            }
        }

        return resampled;
    }

    addVertexColors(geometry, heights) {
        const colors = [];
        
        // Find min/max without spread operator to avoid stack overflow
        let minHeight = heights[0];
        let maxHeight = heights[0];
        for (let i = 1; i < heights.length; i++) {
            if (heights[i] < minHeight) minHeight = heights[i];
            if (heights[i] > maxHeight) maxHeight = heights[i];
        }
        
        const heightRange = maxHeight - minHeight;

        for (let i = 0; i < heights.length; i++) {
            const normalizedHeight = (heights[i] - minHeight) / heightRange;
            
            // Color gradient from blue (low) to green (mid) to brown (high)
            let r, g, b;
            if (normalizedHeight < 0.3) {
                // Blue to green
                const t = normalizedHeight / 0.3;
                r = 0.1 * t;
                g = 0.3 + 0.4 * t;
                b = 0.8 - 0.5 * t;
            } else if (normalizedHeight < 0.7) {
                // Green
                const t = (normalizedHeight - 0.3) / 0.4;
                r = 0.1 + 0.3 * t;
                g = 0.7;
                b = 0.3 - 0.2 * t;
            } else {
                // Green to brown
                const t = (normalizedHeight - 0.7) / 0.3;
                r = 0.4 + 0.3 * t;
                g = 0.7 - 0.4 * t;
                b = 0.1;
            }

            colors.push(r, g, b);
        }

        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    }

    updateCameraPosition(heights) {
        // Find min/max without spread operator to avoid stack overflow
        let minHeight = heights[0];
        let maxHeight = heights[0];
        for (let i = 1; i < heights.length; i++) {
            if (heights[i] < minHeight) minHeight = heights[i];
            if (heights[i] > maxHeight) maxHeight = heights[i];
        }
        const heightRange = maxHeight - minHeight;
        
        // Calculate actual terrain dimensions in meters
        const terrainWidthMeters = this.originalWidth * this.currentGridScale;
        const terrainHeightMeters = this.originalHeight * this.currentGridScale;
        const terrainDiagonal = Math.sqrt(terrainWidthMeters * terrainWidthMeters + terrainHeightMeters * terrainHeightMeters);
        
        // Position camera based on actual terrain size in meters
        // Use the larger of terrain diagonal or height range * 3 for proper viewing distance
        const viewDistance = Math.max(terrainDiagonal * 0.8, heightRange * 3, 500);
        const elevationOffset = Math.max(heightRange * 0.5, viewDistance * 0.2);
        
        // Position camera at 45 degree angle for good overview
        const cameraX = terrainWidthMeters * 0.3;
        const cameraY = maxHeight + elevationOffset;
        const cameraZ = terrainHeightMeters * 0.3;
        
        this.camera.position.set(cameraX, cameraY, cameraZ);
        
        // Look at center of terrain at average height
        const terrainCenterHeight = (minHeight + maxHeight) / 2;
        this.camera.lookAt(0, terrainCenterHeight, 0);
        
        // Update controls target to terrain center
        this.controls.target.set(0, terrainCenterHeight, 0);
        
        // Set appropriate control limits based on terrain size
        this.controls.maxDistance = Math.min(viewDistance * 5, 50000);  // Increased max distance, but keep within far plane
        this.controls.minDistance = Math.max(heightRange * 0.1, 10);
        
        this.controls.update();
        
        console.log(`Camera positioned: terrain ${terrainWidthMeters}x${terrainHeightMeters}m, height range ${heightRange.toFixed(1)}m, distance ${viewDistance.toFixed(1)}m`);
        
        // Update terrain info display
        this.updateTerrainInfoDisplay(minHeight, maxHeight);
    }

    updateTerrainInfoDisplay(minHeight, maxHeight) {
        const terrainWidthMeters = this.originalWidth * this.currentGridScale;
        const terrainHeightMeters = this.originalHeight * this.currentGridScale;
        const heightRange = maxHeight - minHeight;
        
        // Update terrain size display
        document.getElementById('terrainSize').textContent = 
            `地形サイズ: ${terrainWidthMeters.toLocaleString()}m × ${terrainHeightMeters.toLocaleString()}m`;
        
        // Update height range display
        document.getElementById('heightRange').textContent = 
            `標高: ${minHeight.toFixed(1)}m ～ ${maxHeight.toFixed(1)}m (範囲: ${heightRange.toFixed(1)}m)`;
        
        // Update grid scale display
        document.getElementById('gridScale').textContent = 
            `グリッド: ${this.currentGridScale}m (${this.originalWidth} × ${this.originalHeight} ピクセル)`;
    }

    setGridScale(scale) {
        if (this.currentGridScale === scale || !this.heightData) return;
        
        this.currentGridScale = scale;
        
        // Update button states
        document.getElementById('grid1m').classList.toggle('active', scale === 1);
        document.getElementById('grid5m').classList.toggle('active', scale === 5);
        
        // Regenerate mesh with new scale
        this.generateHeightmapMesh();
    }

    resetView() {
        if (this.heightData) {
            // Recalculate mesh dimensions same as in generateHeightmapMesh
            const maxVertices = 2048;
            const aspect = this.originalWidth / this.originalHeight;
            let meshWidth, meshHeight;
            
            if (aspect >= 1) {
                meshWidth = Math.min(this.originalWidth, maxVertices);
                meshHeight = Math.min(Math.round(meshWidth / aspect), maxVertices);
            } else {
                meshHeight = Math.min(this.originalHeight, maxVertices);
                meshWidth = Math.min(Math.round(meshHeight * aspect), maxVertices);
            }
            
            meshWidth = Math.max(meshWidth, 64);
            meshHeight = Math.max(meshHeight, 64);
            
            const heights = this.resampleHeightData(meshWidth, meshHeight);
            this.updateCameraPosition(heights);
        }
    }

    onWindowResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}

// Initialize the viewer when page loads
document.addEventListener('DOMContentLoaded', () => {
    new HeightmapViewer();
});