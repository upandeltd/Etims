frappe.pages["etims-setup-wizard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("eTIMS Setup Wizard"),
		single_column: true,
	});

	page.body.addClass("etims-setup-wizard");

	const steps = [
		{ number: 1, title: __("Company"), icon: "building" },
		{ number: 2, title: __("Environment"), icon: "globe" },
		{ number: 3, title: __("Device"), icon: "cpu" },
		{ number: 4, title: __("Branch"), icon: "git-branch" },
		{ number: 5, title: __("Classifications"), icon: "list" },
		{ number: 6, title: __("Tax Templates"), icon: "file-text" },
		{ number: 7, title: __("Items"), icon: "package" },
		{ number: 8, title: __("Verify"), icon: "check-circle" },
	];

	let current_step = 1;
	let state = {};

	// Render step indicators
	const $steps_bar = $(`<div class="etims-steps-bar"></div>`);
	steps.forEach((s) => {
		$steps_bar.append(
			`<div class="etims-step-indicator" data-step="${s.number}">
				<span class="step-num">${s.number}</span>
				<span>${s.title}</span>
			</div>`
		);
	});
	$(page.body).append($steps_bar);

	const $content = $(`<div class="etims-wizard-content"></div>`);
	$(page.body).append($content);

	function update_step_bar() {
		$steps_bar.find(".etims-step-indicator").each(function () {
			const step = parseInt($(this).data("step"));
			const $num = $(this).find(".step-num");
			$(this).removeClass("active completed");
			if (step < current_step) {
				$(this).addClass("completed");
				$num.html("&#10003;");
			} else if (step === current_step) {
				$(this).addClass("active");
				$num.text(step);
			} else {
				$num.text(step);
			}
		});
	}

	function render_step() {
		$content.empty();
		update_step_bar();

		const render_fn = {
			1: render_step1, 2: render_step2, 3: render_step3, 4: render_step4,
			5: render_step5, 6: render_step6, 7: render_step7, 8: render_step8,
		};
		render_fn[current_step]();
	}

	function add_nav_buttons(can_back, can_next, next_label) {
		const $nav = $(`<div class="wizard-nav"></div>`);
		if (can_back) {
			$nav.append(`<button class="btn btn-default btn-sm">${__("Back")}</button>`);
			$nav.find(".btn-default").on("click", () => { current_step--; render_step(); });
		}
		if (can_next) {
			$nav.append(`<button class="btn btn-primary btn-sm">${next_label || __("Next")}</button>`);
		}
		$content.append($nav);
		return $nav.find(".btn-primary");
	}

	// Step 1: Company
	function render_step1() {
		$content.append(`
			<h4>${__("Select Company")}</h4>
			<p class="text-muted">${__("Choose the company registered with KRA for eTIMS compliance.")}</p>
			<div class="wizard-field company-field"></div>
			<div class="step-result step-alert"></div>
		`);
		const field = frappe.ui.form.make_control({
			df: { fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1 },
			parent: $content.find(".company-field"),
			render_input: true,
		});
		if (state.company) field.set_value(state.company);

		const $next = add_nav_buttons(false, true);
		$next.on("click", () => {
			const company = field.get_value();
			if (!company) { frappe.msgprint(__("Please select a company")); return; }
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step1_validate_company",
				args: { company }, freeze: true,
				callback: (r) => {
					if (r.message.status === "success") {
						state.company = company;
						state.pin = r.message.pin;
						current_step++;
						render_step();
					} else {
						$content.find(".step-result").html(
							`<div class="alert alert-warning">${r.message.message}</div>`
						);
					}
				},
			});
		});
	}

	// Step 2: Environment
	function render_step2() {
		$content.append(`
			<h4>${__("Choose Environment")}</h4>
			<p class="text-muted">${__("Select Sandbox for testing or Production for live KRA integration.")}</p>
			<div class="wizard-field env-field"></div>
			<div class="step-result step-alert"></div>
		`);
		const field = frappe.ui.form.make_control({
			df: { fieldtype: "Select", options: "Sandbox\nProduction", label: __("API Mode"),
				  default: state.api_mode || "Sandbox" },
			parent: $content.find(".env-field"),
			render_input: true,
		});

		const $next = add_nav_buttons(true, true, __("Test Connection"));
		$next.on("click", () => {
			const mode = field.get_value();
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step2_test_connectivity",
				args: { api_mode: mode }, freeze: true, freeze_message: __("Testing connection..."),
				callback: (r) => {
					if (r.message.status === "success") {
						state.api_mode = mode;
						$content.find(".step-result").html(
							`<div class="alert alert-success">${r.message.message}</div>`
						);
						setTimeout(() => { current_step++; render_step(); }, 1000);
					} else {
						$content.find(".step-result").html(
							`<div class="alert alert-danger">${r.message.message}</div>`
						);
					}
				},
			});
		});
	}

	// Step 3: Device
	function render_step3() {
		$content.append(`
			<h4>${__("Initialize Device")}</h4>
			<p class="text-muted">${__("Register your eTIMS device with KRA.")}</p>
			<div class="wizard-field branch-field"></div>
			<div class="wizard-field serial-field"></div>
			<div class="step-result step-alert"></div>
		`);
		const branch_field = frappe.ui.form.make_control({
			df: { fieldtype: "Data", label: __("Branch ID (e.g. 00 for head office)"), reqd: 1 },
			parent: $content.find(".branch-field"), render_input: true,
		});
		if (state.branch_id) branch_field.set_value(state.branch_id);

		const serial_field = frappe.ui.form.make_control({
			df: { fieldtype: "Data", label: __("Device Serial Number"), reqd: 1 },
			parent: $content.find(".serial-field"), render_input: true,
		});

		const $next = add_nav_buttons(true, true, __("Initialize"));
		$next.on("click", () => {
			const branch = branch_field.get_value();
			const serial = serial_field.get_value();
			if (!branch || !serial) { frappe.msgprint(__("Fill in all fields")); return; }
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step3_initialize_device",
				args: { company: state.company, branch_id: branch,
						serial_number: serial, api_mode: state.api_mode || "Sandbox" },
				freeze: true, freeze_message: __("Initializing device with KRA..."),
				callback: (r) => {
					if (r.message.status === "success") {
						state.branch_id = branch;
						$content.find(".step-result").html(
							`<div class="alert alert-success">${r.message.message}</div>`
						);
						setTimeout(() => { current_step = 5; render_step(); }, 1000);
					} else {
						$content.find(".step-result").html(
							`<div class="alert alert-danger">${r.message.message}</div>`
						);
					}
				},
			});
		});
	}

	// Step 4: Branch (auto-done in step 3)
	function render_step4() {
		$content.append(`
			<h4>${__("Branch Assignment")}</h4>
			<p class="text-muted">${__("Branch was auto-assigned during device initialization.")}</p>
			<div class="alert alert-success">${__("Branch {0} assigned to your user.", [state.branch_id || "00"])}</div>
		`);
		add_nav_buttons(true, true).on("click", () => { current_step++; render_step(); });
	}

	// Step 5: Classifications
	function render_step5() {
		$content.append(`
			<h4>${__("Fetch Item Classifications")}</h4>
			<p class="text-muted">${__("Download item classification codes from KRA. This may take a moment.")}</p>
			<div class="step-result step-alert"></div>
		`);
		const $next = add_nav_buttons(true, true, __("Fetch Classifications"));
		$next.on("click", () => {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step5_fetch_classifications",
				freeze: true, freeze_message: __("Fetching from KRA..."),
				callback: (r) => {
					if (r.message.status === "success") {
						$content.find(".step-result").html(
							`<div class="alert alert-success">
								${__("Created {0} classifications. Total: {1}", [r.message.created, r.message.total])}
							</div>`
						);
						setTimeout(() => { current_step++; render_step(); }, 1500);
					} else {
						$content.find(".step-result").html(
							`<div class="alert alert-danger">${r.message.message}</div>`
						);
					}
				},
			});
		});
	}

	// Step 6: Tax Templates
	function render_step6() {
		$content.append(`
			<h4>${__("Create Tax Templates")}</h4>
			<p class="text-muted">${__("Auto-create Item Tax Templates for KRA tax codes A through E.")}</p>
			<div class="step-result step-alert"></div>
		`);
		const $next = add_nav_buttons(true, true, __("Create Templates"));
		$next.on("click", () => {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step6_create_tax_templates",
				args: { company: state.company }, freeze: true,
				callback: (r) => {
					if (r.message.status === "success") {
						$content.find(".step-result").html(
							`<div class="alert alert-success">${__("Created {0} tax templates.", [r.message.created])}</div>`
						);
						setTimeout(() => { current_step++; render_step(); }, 1000);
					}
				},
			});
		});
	}

	// Step 7: Items
	function render_step7() {
		$content.append(`
			<h4>${__("Register Items")}</h4>
			<p class="text-muted">${__("Register unregistered items with eTIMS. Items need a classification code first.")}</p>
			<div class="step-result step-alert"></div>
		`);
		const $next = add_nav_buttons(true, true, __("Register Items"));
		$next.on("click", () => {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.setup_wizard.step7_bulk_register_items",
				args: { limit: 50 }, freeze: true,
				freeze_message: __("Registering items..."),
				callback: (r) => {
					if (r.message) {
						const m = r.message;
						$content.find(".step-result").html(
							`<div class="alert alert-${m.failed ? 'warning' : 'success'}">
								${__("{0} of {1} items registered. {2} failed.", [m.success || 0, m.total || 0, m.failed || 0])}
							</div>`
						);
						setTimeout(() => { current_step++; render_step(); }, 1500);
					}
				},
			});
		});

		// Skip button
		$content.append(
			`<p class="skip-link-wrapper"><a href="#" class="skip-link text-muted">${__("Skip — I'll register items later")}</a></p>`
		);
		$content.find(".skip-link").on("click", (e) => {
			e.preventDefault();
			current_step++;
			render_step();
		});
	}

	// Step 8: Verify
	function render_step8() {
		$content.append(`
			<h4>${__("Verification")}</h4>
			<p class="text-muted">${__("Checking your eTIMS configuration...")}</p>
			<div class="wizard-checks-list"></div>
			<div class="step-result step-alert"></div>
		`);

		frappe.call({
			method: "kenya_etims_compliance.custom_methods.setup_wizard.step8_verify_setup",
			freeze: true,
			callback: (r) => {
				if (r.message) {
					const $list = $content.find(".wizard-checks-list");
					r.message.checks.forEach((c) => {
						const icon = c.passed ? "&#10003;" : "&#10007;";
						const icon_class = c.passed ? "passed" : "failed";
						$list.append(
							`<div class="wizard-check">
								<span class="wizard-check-icon ${icon_class}">${icon}</span>
								<span>${c.check}</span>
							</div>`
						);
					});

					if (r.message.all_passed) {
						$content.find(".step-result").html(
							`<div class="alert alert-success">
								<b>${__("Setup Complete!")}</b> ${__("Your eTIMS integration is ready.")}
							</div>`
						);
					} else {
						$content.find(".step-result").html(
							`<div class="alert alert-warning">
								${__("Some checks failed. Review and fix the issues above.")}
							</div>`
						);
					}

					// Done button
					$content.append(
						`<div class="wizard-actions">
							<button class="btn btn-primary btn-sm done-btn">${__("Go to eTIMS Compliance")}</button>
						</div>`
					);
					$content.find(".done-btn").on("click", () => {
						frappe.set_route("app", "etims-compliance");
					});
				}
			},
		});

		add_nav_buttons(true, false);
	}

	// Load initial status and start
	frappe.call({
		method: "kenya_etims_compliance.custom_methods.setup_wizard.get_setup_status",
		callback: (r) => {
			if (r.message) {
				state = r.message;
				// Auto-advance past completed steps
				if (state.company) current_step = 2;
				if (state.device_initialized) current_step = 5;
				if (state.classifications_fetched) current_step = 6;
				if (state.tax_templates_exist) current_step = 7;
			}
			render_step();
		},
	});
};
