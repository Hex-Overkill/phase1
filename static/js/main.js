function filterProducts() {
    const search = document.getElementById('searchInput').value;
    const category = document.getElementById('categoryFilter').value;
    const sort = document.getElementById('sortFilter').value;
    
    const params = new URLSearchParams({
        q: search,
        category: category,
        sort: sort
    });
    
    window.location.href = `/dashboard?${params}`;
}

// Real-time search
document.getElementById('searchInput')?.addEventListener('input', function() {
    clearTimeout(this.timeout);
    this.timeout = setTimeout(filterProducts, 500);
});

// Image preview for upload
document.querySelectorAll('input[type="file"]').forEach(input => {
    input.addEventListener('change', function(e) {
        const files = Array.from(e.target.files);
        const preview = document.getElementById('imagePreview');
        if (preview) {
            preview.innerHTML = '';
            files.slice(0, 4).forEach(file => {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.className = 'img-thumbnail me-2 mb-2';
                    img.style.width = '100px';
                    img.style.height = '100px';
                    img.style.objectFit = 'cover';
                    preview.appendChild(img);
                }
                reader.readAsDataURL(file);
            });
        }
    });
});

// Admin category add
document.getElementById('addCategoryBtn')?.addEventListener('click', function() {
    const name = document.getElementById('newCategoryName').value;
    if (name) {
        fetch('/admin/add_category', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            }
        });
    }
});