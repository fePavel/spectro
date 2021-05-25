using DelimitedFiles
using Distributed
using Random

#import RobustPmap

@everywhere using SpecialFunctions
@everywhere include("profiles.jl")
@everywhere using PyCall
@everywhere using Combinatorics


function fitMCMC(spec, ppar, add; sampler="Affine", tieds=Dict(), prior=nothing, nwalkers=100, nsteps=1000, nthreads=1, thinning=1, init=nothing, opts=0)

    #COUNTERS["num"] = nwalkers

	println(init)

    pars = make_pars(ppar, tieds=tieds)
    priors = make_priors(prior)
	println(priors)
    params = [p.val for (k, p) in pars if p.vary == 1]

    numdims = size(params)[1]

	#lnlike = p->begin
	function lnlike(p)
		i = 1
		#println(pars)
		for (k, v) in pars
			if v.vary == 1
				#println(i, " ", p[i], " ", v.min)
				if p[i] < v.min
					p[i] = v.min
				elseif p[i] > v.max
					p[i] = v.max
				end
				pars[k].val = p[i]
				i += 1
			end
		end

		update_pars(pars, spec, add)

		retval = 0

		if priors != nothing
			for (k, p) in priors
				#println(p.name, " ", pars[p.name].val, " ", use_prior(p, pars[p.name].val))
				retval -= use_prior(p, pars[p.name].val)
			end
		end

		for s in spec
			if sum(s.mask) > 0
				model = calc_spectrum(s, pars, out="init")
				retval -= .5 * sum(((model .- s.y[s.mask]) ./ s.unc[s.mask]) .^ 2)

				if opts["hier_continuum"] == true
					for cont in s.cont
						mask = (s.x[s.mask] .> cont.left) .& (s.x[s.mask] .< cont.right)
						c = parse(Float64, split(pars[cont.c[1]].addinfo, "_")[4])
						A = sum((model[mask] .* c ./ s.unc[s.mask][mask]) .^ 2) + 1 / pars["hcont"].val ^ 2
						B = sum(model[mask] .* c .* (model[mask] .- s.y[s.mask][mask]) ./ s.unc[s.mask][mask] .^ 2)
						retval -= .5 * (log(A * pars["hcont"].val ^ 2) - B ^ 2 / A)
					end
				end
			end
		end

		# add constraints to the fit set by opts parameter

		# constraints for H2 on increasing b parameter with J level increase
		if opts["b_increase"] == true
			for (k, v) in pars
				if occursin("H2j", k) & occursin("b_", k)
					for (k1, v1) in pars
						if occursin(k[1:7], k1) & ~occursin(k, k1)
							j, j1 = parse(Int64, k[8:end]), parse(Int64, k1[8:end])
							x = sign(j - j1) * (v.val / v1.val - 1) * 10
							retval -= (x < 0 ? x : 0) ^ 2
						end
					end
				end
			end
		end

		# constraints for H2 on on excitation diagram to be gradually increasing with J
		if opts["H2_excitation"] == true
			T = Dict()
			E = [170.5, 339.35, 505.31, 666.53, 822.20, 970.58, 1111.96, 1243.40, 1367.25, 1480.35] #Energy difference in K
			g = [(2 * level + 1) * ((level % 2) * 2 + 1) for level in 0:11]  #statweights
			for (k, v) in pars
				if occursin("H2j", k) & occursin("N_", k)
					j = parse(Int64, k[8:end])
					if haskey(pars, k[1:7] * string(j+1))
						if ~haskey(T, k[3])
							T[k[3]] = Dict()
						end
						#println(j, " ", v.val, " ", E[j+1], " ", g[j+1])
						T[k[3]][j] = E[j+1] / log(10^v.val / 10^pars[k[1:7] * string(j+1)].val * g[j+2] / g[j+1])
					end
				end
			end
			for (k, d) in T
				#println(k)
				for (k, v) in d
					if haskey(d, k+1)
						#println(k, " ", v, " ", d[k+1])
						retval -= (d[k+1] - v < 0 ? (d[k+1] - v) / 50 : 0) ^ 2 + (v < 0 ? v / 100 : 0) ^ 2
					end
				end
			end
			#println(T)
		end

		return retval
	end

	if sampler in ["Affine", "ESS", "UltraNest"]
		if nprocs() > 1
			rmprocs(2:nprocs())
		end

		nthreads = 1
		open("config/options.ini") do f
			for l in eachline(f)
				if occursin("MCMC_threads", l)
					nthreads = parse(Int64, split(l)[3])
					println(nthreads)
				end
			end
		end

		println(nthreads)
		if nthreads > 1
			addprocs(nthreads - 1)
		end

		@everywhere include("profiles.jl")

		println("procs: ", nprocs())
	end

	if sampler == "Affine"
		bounds = hcat([p.min for (k, p) in pars if p.vary], [p.max for (k, p) in pars if p.vary])
		#println(bounds)
		chain, llhoodvals = sampleAffine(lnlike, nwalkers, init, nsteps, thinning, bounds)

	elseif sampler == "ESS"
		bounds = hcat([p.min for (k, p) in pars if p.vary], [p.max for (k, p) in pars if p.vary])
		chain, llhoodvals = sampleESS(lnlike, nwalkers, init, nsteps, thinning, bounds)

	elseif sampler == "Hamiltonian"
		"""
		does not work yet
		"""
		#chain = sampleHMC(lnlike, init, nsteps)
		x0 = init[:,1]

		# Define a Hamiltonian system
		metric = DiagEuclideanMetric(size(x0)[1])
		hamiltonian = Hamiltonian(metric, lnlike, ForwardDiff)

		# Define a leapfrog solver, with initial step size chosen heuristically
		initial_ϵ = find_good_stepsize(hamiltonian, x0)
		integrator = Leapfrog(initial_ϵ)

		# Define an HMC sampler, with the following components
		#   - multinomial sampling scheme,
		#   - generalised No-U-Turn criteria, and
		#   - windowed adaption for step-size and diagonal mass matrix
		proposal = NUTS{MultinomialTS, GeneralisedNoUTurn}(integrator)
		adaptor = StanHMCAdaptor(MassMatrixAdaptor(metric), StepSizeAdaptor(0.8, integrator))

		# Run the sampler to draw samples from the specified Gaussian, where
		#   - `samples` will store the samples
		#   - `stats` will store diagnostic statistics for each sample
		samples, stats = sampleAffine(hamiltonian, proposal, initial_θ, nsteps, adaptor, nsteps/2; progress=true)

	elseif sampler == "UltraNest"
		ultranest = pyimport("ultranest")

		mytransform = cube->begin
			params = copy(cube)
			hi, lo = [p.max for (k, p) in pars if p.vary], [p.min for (k, p) in pars if p.vary]
			for (i, c) in enumerate(cube)
				params[i] = c * (hi[i] - lo[i]) + lo[i]
			end
			return params
		end

		lnlike_vec = p-> begin
			return pmap(lnlike, mapslices(x->[x], p, dims=2)[:])
		end

		mytransform_vec = cube->begin
			return transpose(reduce(hcat, map(i->mytransform(cube[i, :]), 1:size(cube, 1))))
		end

		paramnames = [replace(p.name, "_"=>"") for (k, p) in pars if p.vary]
		sampler = ultranest.ReactiveNestedSampler(paramnames, lnlike_vec, transform=mytransform_vec, vectorized=true)
		results = sampler.run()
		print("result has these keys:", keys(results), "\n")

		println(results["samples"])
		println(results["maximum_likelihood"])

		sampler.print_results()
		#sampler.plot_run()
		#sampler.plot()
		#return results["samples"], nothing
		return results, nothing
	end
end

function check_pars(proposal, pars)
    return all([proposal[i] > p.min && proposal[i] < p.max for (i, p) in enumerate([p for p in pars if p.vary])])
end

function sampleAffine(llhood::Function, nwalkers::Int, x0::Array, nsteps::Integer, thinning::Integer, bounds::Array; a::Number=2.)
    """
    Modified version of AffineInvariantMCMC by MADS (see copyright information in initial module)
    """
	@assert length(size(x0)) == 2
	x = copy(x0)
	print(size(x))
	chain = Array{Float64}(undef, nwalkers, size(x0, 2), div(nsteps, thinning))
	llhoodvals = Array{Float64}(undef, nwalkers, div(nsteps, thinning))
	lastllhoodvals = pmap(llhood, map(i->x[i, :], 1:size(x, 1)))
	chain[:, :, 1] = x0
	llhoodvals[:, 1] = lastllhoodvals
	for i = 2:nsteps
		println(i)
		s = shuffle(collect(1:nwalkers))
		for ensembles in [(s[1:div(nwalkers, 2)], s[div(nwalkers, 2) + 1:nwalkers]), (s[div(nwalkers, 2) + 1:nwalkers], s[1:div(nwalkers, 2)])]
			active, inactive = ensembles
			zs = map(u->((a - 1) * u + 1)^2 / a, rand(length(active)))
			proposals = map(i-> min.(max.(zs[i] * x[active[i], :] + (1 - zs[i]) * x[rand(inactive), :], bounds[:,1]), bounds[:,2]), 1:length(active))
            newllhoods = pmap(llhood, proposals)
			for (j, walkernum) in enumerate(active)
				logratio = (size(x, 2) - 1) * log(zs[j]) + newllhoods[j] - lastllhoodvals[walkernum]
				if log(rand()) < logratio
					lastllhoodvals[walkernum] = newllhoods[j]
					x[walkernum, :] = proposals[j]
			    end
				if i % thinning == 0
					chain[walkernum, :, div(i, thinning)] = x[walkernum, :]
					llhoodvals[walkernum, div(i, thinning)] = lastllhoodvals[walkernum]
				end
			end
		end
		open("output/mcmc_last.dat", "w") do io
			writedlm(io, chain[:, :, i], " ")
		end
	end
	return chain, llhoodvals
end

function sampleESS(llhood::Function, nwalkers::Int, x0::Array, nsteps::Integer, thinning::Integer, bounds::Array; mu::Number=1.)
	"""
	Ensamble Slice Sampler. Rewritten based on zeus python package
	"""
	function get_directions(x, mu)
		nsamples = size(x, 1)
		inds = hcat(rand(collect(permutations((1:nsamples), 2)), nsamples)...)
		return 2. .* mu .* (x[inds[1,:], :] .- x[inds[2,:], :])
	end

	maxsteps, maxiters = 100, 100
	#println(bounds)
	@assert length(size(x0)) == 2
	ndims = size(x0, 2)
	x = copy(x0)
	chain = Array{Float64}(undef, nwalkers, ndims, div(nsteps, thinning))
	llhoodvals = Array{Float64}(undef, nwalkers, div(nsteps, thinning))
	lastllhoodvals = pmap(llhood, map(i->x[i, :], 1:nwalkers))
	chain[:, :, 1] = x0
	llhoodvals[:, 1] = lastllhoodvals
	ncalls = 0

	for i = 2:nsteps
		println(i)
		# Initialise number of Log prob calls
		nexp, ncon, ncall = 0, 0, 0

		s = shuffle(collect(1:nwalkers))
		for ensembles in [(s[1:div(nwalkers, 2)], s[div(nwalkers, 2) + 1:nwalkers]), (s[div(nwalkers, 2) + 1:nwalkers], s[1:div(nwalkers, 2)])]
			# Define active-inactive ensembles
			active, inactive = ensembles
			#println(active, " ", inactive)

			# Compute directions
			directions = get_directions(x[inactive, :], mu)
			#println("direct ", directions)

			# Get Z0 = LogP(x0)
			z0 = lastllhoodvals[active] .- randexp(div(nwalkers, 2))

			# Set Initial Interval Boundaries
			L = - rand(Float64, div(nwalkers, 2))
			R = L .+ 1.0
			#println(L, " ", R)

			# Parallel stepping-out
			J = rand(0:maxsteps-1, div(nwalkers, 2))
			K = (maxsteps .- 1) .- J
			#println(J, " ", K)

			# Stepping-out initialisation
			mask_J, Z_L, X_L = trues(div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2), ndims)
			mask_K, Z_R, X_R = trues(div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2), ndims)
			#println(mask_K, Z_R, X_R)

			cnt = 0
			# Stepping-Out procedure
			while (sum(mask_J) > 0) | (sum(mask_K) > 0)
				cnt = sum(mask_J) > 0 ? cnt + 1 : cnt
				cnt = sum(mask_K) > 0 ? cnt + 1 : cnt
				if cnt > maxiters
					throw(DomainError("Number of expansion exceed limit"))
				end

				mask_J[mask_J] = J[mask_J] .> 0
				mask_K[mask_K] = K[mask_K] .> 0
				#println(cnt, " mask ", mask_J, " ", mask_K)

				X_L[mask_J, :] = min.(max.(directions[mask_J, :] .* L[mask_J] .+ x[active, :][mask_J, :], transpose(bounds[:, 1])), transpose(bounds[:, 2]))
				X_R[mask_K, :] = min.(max.(directions[mask_K, :] .* R[mask_K] .+ x[active, :][mask_K, :], transpose(bounds[:, 1])), transpose(bounds[:, 2]))
				#println("X: ", X_L, " ", X_R)

				if sum(mask_J) + sum(mask_K) < 1
					cnt -= 1
				else
					Z_LR_masked = pmap(llhood, map(i->vcat(X_L[mask_J, :], X_R[mask_K, :])[i, :], 1:sum(mask_J)+sum(mask_K)))
					Z_L[mask_J] .= Z_LR_masked[begin:sum(mask_J)]
					Z_R[mask_K] .= Z_LR_masked[sum(mask_J)+1:end]
					ncall += sum(mask_J) + sum(mask_K)
				end

				m = z0[mask_J] .< Z_L[mask_J]
				mask_J[mask_J] .= m
				if sum(m) > 0
					L[mask_J] .-= 1
					J[mask_J] .-= 1
				end
				nexp += sum(m)
				m = z0[mask_K] .< Z_R[mask_K]
				mask_K[mask_K] .= m
				if sum(m) > 0
					R[mask_K] .+= 1
					K[mask_K] .-= 1
				end
				nexp += sum(m)
			end
			#println(X_L, " ", X_R)

			# Shrinking procedure
			Widths, z_prime, x_prime = Array{Float64}(undef, div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2)), Array{Float64}(undef, div(nwalkers, 2), ndims)
			mask = trues(div(nwalkers, 2))

			cnt = 0
			while sum(mask) > 0
				# Update Widths of intervals
				Widths[mask] = L[mask] .+ rand(Float64, sum(mask)) .* (R[mask] .- L[mask])

				# Compute New Positions
				x_prime[mask, :] .= min.(max.(directions[mask, :] .* Widths[mask] .+ x[active, :][mask, :], transpose(bounds[:, 1])), transpose(bounds[:, 2]))

				# Calculate LogP of New Positions
				z_prime[mask] = pmap(llhood, map(i->x_prime[mask, :][i, :], 1:sum(mask)))

				ncall += sum(mask)

				# Shrink slices
				mask[mask] .= z0[mask] .> z_prime[mask]
				#println(mask)
				#println(L, " ", R)
				for (j, w) in enumerate(Widths)
					if mask[j] == 1
						if Widths[j] < 0
							L[j] = Widths[j]
						else
							R[j] = Widths[j]
						end
					end
				end
				#println(L, " ", R)
				ncon += sum(mask)

				cnt += 1
				if cnt > maxiters
					throw(DomainError("Number of contractions exceeded maximum limit!"))
				end
			end
			x[active, :] = x_prime[:, :]
			lastllhoodvals[active] = z_prime[:]
			if i % thinning == 0
				chain[active, :, i] .= x_prime[:, :]
				llhoodvals[active, i] .= z_prime[:]
			end
		end
		#println(mu)
		nexp = max(1, nexp)
		mu *= 2.0 * nexp / (nexp + ncon)
		ncalls += ncall
	end
	return chain, llhoodvals
end


@everywhere using AdvancedHMC, ForwardDiff

function sampleHMC(llhood::Function, x0::Array, nsteps::Integer)
    """
    Hamiltonian MCMC sampling using Turing.jl package
    """
	init = x0[:,1]
	#lastllhoodvals = RobustPmap.rpmap(llhood, map(i->x[:, i], 1:size(x, 2)))

	# Define a Hamiltonian system
	metric = DiagEuclideanMetric(size(init)[1])
	hamiltonian = Hamiltonian(metric, llhood, ForwardDiff)

	# Define a leapfrog solver, with initial step size chosen heuristically
	initial_ϵ = find_good_stepsize(hamiltonian, init)
	integrator = Leapfrog(initial_ϵ)

	# Define an HMC sampler, with the following components
	#   - multinomial sampling scheme,
	#   - generalised No-U-Turn criteria, and
	#   - windowed adaption for step-size and diagonal mass matrix
	proposal = NUTS{MultinomialTS, GeneralisedNoUTurn}(integrator)
	adaptor = StanHMCAdaptor(MassMatrixAdaptor(metric), StepSizeAdaptor(0.8, integrator))

	# Run the sampler to draw samples from the specified Gaussian, where
	#   - `samples` will store the samples
	#   - `stats` will store diagnostic statistics for each sample
	samples, stats = sample(hamiltonian, proposal, initial_θ, nsteps, adaptor, nsteps/2; progress=true)
	return samples
end