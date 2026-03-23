        const dropArea = document.getElementById('dropArea');
        const fileInput = document.getElementById('fileInput');
        const preview = document.getElementById('preview');
        const form = document.getElementById('uploadForm');
        const loadingDiv = document.getElementById('loading');
        const resultsDiv = document.getElementById('results');
        const skinToneSpan = document.getElementById('skinTone');
        const rgbSpan = document.getElementById('rgb');
        const styleSummaryH3 = document.getElementById('styleSummary');
        const outfitDiv = document.getElementById('outfitSuggestions');
        const productDiv = document.getElementById('productList');
        const tipsP = document.getElementById('stylingTips');
        const submitBtn = document.getElementById('submitBtn');

        // Drag & Drop
        dropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropArea.style.borderColor = '#007bff';
        });

        dropArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropArea.style.borderColor = '#aaa';
        });

        dropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dropArea.style.borderColor = '#aaa';
            const file = e.dataTransfer.files[0];
            if (file) {
                fileInput.files = e.dataTransfer.files;
                showPreview(file);
            }
        });

        dropArea.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) showPreview(file);
        });

        function showPreview(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                preview.src = e.target.result;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }

        // Form submission
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);

            // Disable button and show loading
            submitBtn.disabled = true;
            loadingDiv.style.display = 'block';
            resultsDiv.style.display = 'none';

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.error) {
                    alert(data.error);
                    submitBtn.disabled = false;
                    loadingDiv.style.display = 'none';
                    return;
                }

                // Populate results
                skinToneSpan.textContent = data.skin_tone;
                rgbSpan.textContent = `${data.rgb[0]}, ${data.rgb[1]}, ${data.rgb[2]}`;
                styleSummaryH3.textContent = data.recommendations.style_summary || 'Your Style';
                tipsP.textContent = data.recommendations.styling_tips || 'No tips available.';

                // Outfit suggestions - UPDATED WITH SAFETY CHECK
                let outfitHtml = '';
                const outfits = data.recommendations.outfit_suggestions || {};
                for (const [category, items] of Object.entries(outfits)) {
                    if (items && Array.isArray(items) && items.length) {
                        outfitHtml += `
                            <div class="outfit-category">
                                <strong>${category.charAt(0).toUpperCase() + category.slice(1)}</strong>
                                <ul>
                                    ${items.map(item => `<li>${item}</li>`).join('')}
                                </ul>
                            </div>
                        `;
                    }
                }
                outfitDiv.innerHTML = outfitHtml || '<p>No specific outfit suggestions available.</p>';

                // Product recommendations
                let productHtml = '';
                const products = data.recommendations.product_recommendations || [];
                products.forEach(prod => {
                    productHtml += `
                        <div class="product-card">
                            <h4>${prod.name || 'Product'}</h4>
                            <p>${prod.description || ''} - <strong>${prod.price || 'N/A'}</strong></p>
                            <a href="${prod.purchase_link || '#'}" target="_blank">View Item</a>
                        </div>
                    `;
                });
                if (productHtml === '') {
                    productHtml = '<p>No specific product links available right now.</p>';
                }
                productDiv.innerHTML = productHtml;

                // Show results
                resultsDiv.style.display = 'block';
                submitBtn.disabled = false;
                loadingDiv.style.display = 'none';

            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred loading your results. Please try again.');
                submitBtn.disabled = false;
                loadingDiv.style.display = 'none';
            }
        });
