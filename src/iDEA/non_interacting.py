"""Contains all non-interacting functionality and solvers."""


import copy
import numpy as np
import scipy as sp
import numpy.linalg as npla
import scipy.linalg as spla
import iDEA.system


def kinetic_energy_operator(s: iDEA.system.System) -> np.ndarray:
    """
    Compute single-particle kinetic energy operator as a matrix.

    This is built using a given number of finite differences to represent the second derivative.
    The number of differences taken is defined in s.stencil.

    Args:
        s: iDEA.system.System, System object.

    Returns:
        K: np.ndarray, Kintetic energy operator.
    """
    if s.stencil == 3:
        sd = 1.0 * np.array([1, -2, 1], dtype=np.float) / s.dx ** 2
        sdi = (-1, 0, 1)
    elif s.stencil == 5:
        sd = 1.0 / 12.0 * np.array([-1, 16, -30, 16, -1], dtype=np.float) / s.dx ** 2
        sdi = (-2, -1, 0, 1, 2)
    elif s.stencil == 7:
        sd = (1.0 / 180.0 * np.array([2, -27, 270, -490, 270, -27, 2], dtype=np.float) / s.dx ** 2)
        sdi = (-3, -2, -1, 0, 1, 2, 3)
    elif s.stencil == 9:
        sd = (1.0 / 5040.0 * np.array([-9, 128, -1008, 8064, -14350, 8064, -1008, 128, -9], dtype=np.float) / s.dx ** 2)
        sdi = (-4, -3, -2, -1, 0, 1, 2, 3, 4)
    elif s.stencil == 11:
        sd = (1.0 / 25200.0 * np.array([8, -125, 1000, -6000, 42000, -73766, 42000, -6000, 1000, -125, 8], dtype=np.float,) / s.dx ** 2)
        sdi = (-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5)
    elif s.stencil == 13:
        sd = (1.0 / 831600.0 * np.array([-50, 864, -7425,44000, -222750, 1425600, -2480478, 1425600, -222750, 44000, -7425, 864, -50], dtype=np.float) / s.dx ** 2)
        sdi = (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)
    second_derivative = np.zeros((s.x.shape[0], s.x.shape[0]))
    for i in range(len(sdi)):
        second_derivative += np.diag(np.full(np.diag(np.zeros((s.x.shape[0], s.x.shape[0])), k=sdi[i]).shape[0], sd[i]), k=sdi[i])
    K = -0.5 * second_derivative
    return K


def external_potential_operator(s: iDEA.system.System) -> np.ndarray:
    """
    Compute single-particle external potential energy operator as a matrix.

    Args:
        s: iDEA.system.System, System object.

    Returns:
        Vext: np.ndarray, External potential energy operator.
    """
    Vext = np.diag(s.v_ext)
    return Vext


def hamiltonian(s: iDEA.system.System, K: np.ndarray = None, V: np.ndarray = None) -> np.ndarray:
    """
    Compute the Hamiltonian from the kinetic and potential terms.

    Args:
        s: iDEA.system.System, System object.
        K: np.ndarray, Single-particle kinetic energy operator [If None this will be computed from s]. (default = None)
        V: np.ndarray, Potential energy operator [If None this will be computed from s]. (default = None)

    Returns:
        H: np.ndarray, Hamiltonian.
    """
    if K is None:
        K = kinetic_energy_operator(s)
    if V is None:
        V = external_potential_operator(s)
    H = K + V
    return H


def solve_state(s, H=None, k: int = 0):
    """
    Solves for the non-interacting eigenstate of the given system.

    Args:
        s: iDEA.system.System, System object.
        H: np.ndarray, Hamiltonian [If None this will be computed from s]. (default = None)
        k: int, Energy state to solve for. (default = 0, the ground-state)

    Returns:
        state: iDEA.state.SingleBodyState, solved ground_state.
    """
    # Construct the Hamiltonian.
    if H is None:
        H = hamiltonian(s)

    # Solve the state and normalise orbitals.
    energies, orbitals = spla.eigh(H)
    orbitals = orbitals / np.sqrt(s.dx) 

    # Construct the single-body state.
    state = iDEA.state.SingleBodyState()
    state.up.energies = copy.deepcopy(energies)
    state.down.energies = copy.deepcopy(energies)
    state.up.orbitals = copy.deepcopy(orbitals)
    state.down.orbitals = copy.deepcopy(orbitals)
    calculate_occupations(s, state, k)
    return state


def calculate_occupations(s, state, k):
    # Count number of electrons in each spin channel.
    N_up = s.electrons.count('u')
    N_down = s.electrons.count('d')

    # Initialise occupations to 0.
    state.up.occupations = np.zeros(shape = state.up.energies.shape, dtype=np.float)
    state.down.occupations = np.zeros(shape = state.down.energies.shape, dtype=np.float)
    assert state.up.occupations.shape == state.down.occupations.shape, f"Occuations must have same shape for up and down spin channels."

    # Compute the ground state occupations.
    state.up.occupations[:N_up] = 1.0
    state.down.occupations[:N_down] = 1.0 

    print(state.up.occupations[:8].astype(np.int))
    print(state.down.occupations[:8].astype(np.int))
    print(total_energy(s, state))
    print('-----------')

    # Compute higher energy states.
    for _ in range(1, k+1):
        
        # Get the lumos for the current state, as possible excitations. 
        up_args = np.argwhere(state.up.occupations == 1.0)
        down_args = np.argwhere(state.down.occupations == 1.0)
        up_lumo = np.max(up_args) + 1
        down_lumo = np.max(down_args) + 1

        # Try all possible up excitations.
        up_trial_energies = []
        up_trial_states = []
        for ua in up_args:
            state_copy = copy.deepcopy(state)
            state_copy.up.occupations[ua] = 0.0
            state_copy.up.occupations[up_lumo] = 1.0
            E = total_energy(s, state_copy)
            up_trial_energies.append(E)
            up_trial_states.append(state_copy)

        # Try all possible down excitations.
        down_trial_energies = []
        down_trial_states = []
        for da in down_args:
            state_copy = copy.deepcopy(state)
            state_copy.down.occupations[da] = 0.0
            state_copy.down.occupations[down_lumo] = 1.0
            E = total_energy(s, state_copy)
            down_trial_energies.append(E)
            down_trial_states.append(state_copy)

        # Replace the state with the correct state.
        up_argmax = np.argmax(up_trial_energies)
        down_argmax = np.argmax(down_trial_energies)
        if up_trial_energies[up_argmax] >= down_trial_energies[down_argmax]:
            state = copy.deepcopy(up_trial_states[up_argmax])
            print('true')
        else:
            print('false')
            state = copy.deepcopy(down_trial_states[down_argmax])
        print(state.up.occupations[:8].astype(np.int))
        print(state.down.occupations[:8].astype(np.int))
        print(total_energy(s, state))
        print('-----------')
        # TODO: Fix up and down seperation error here.


def total_energy(s, state):
    E = np.sum(state.up.energies * state.up.occupations) + np.sum(state.down.energies * state.down.occupations)
    return E










# def charge_density(s, orbitals):
#     r"""Compute charge density from given non-interacting orbitals.

#     .. math:: n(x) = \sum_j^\mathrm{occ} = \phi_j^*(x)\phi_j(x)

#     s: System
#         System object.
#     orbitals: np.ndarray
#         Array of normalised orbitals, indexed as orbitals[space,orbital_number] or [time,space,orbital_number].

#     returns:
#     n: np.ndarray
#         Charge density. indexed as [space] or [time,space]
#     """
#     if len(orbitals.shape) == 3:
#         n = np.zeros(shape=(orbitals.shape[0], orbitals.shape[1]))
#         for j in range(orbitals.shape[0]):
#             n[j, :] = charge_density(s, orbitals[j, :, :])
#         return n
#     elif len(orbitals.shape) == 2:
#         occupied = orbitals[:, : s.NE]
#         n = np.sum(occupied.conj() * occupied, axis=1).real
#         return n
#     else:
#         pass  # TODO 


# def probability_density(s, orbitals):
#     r"""Compute probability density from given non-interacting orbitals.

#     .. math:: n(x) =\frac{1}{N} \sum_j^\mathrm{occ} \phi_j^*(x)\phi_j(x)

#     s: System
#         System object.
#     orbitals: np.ndarray
#         Array of normalised orbitals, indexed as orbitals[space,orbital_number].

#     returns:
#     n: np.ndarray
#         Charge density.
#     """
#     occupied = orbitals[:, : s.NE]
#     n = np.sum(occupied.conj() * occupied, axis=1).real / s.NE
#     return n


# def orbital_density(s, orbital):
#     r"""Compute charge density for a given non-interacting orbital.

#     .. math:: n(x) = \phi^*(x)\phi(x)

#     s: System
#         System object.
#     orbital: np.ndarray
#         Normalised orbital.

#     returns:
#     n: np.ndarray
#         Orbital density.
#     """
#     n = (orbital.conj() * orbital).real
#     return n


# def one_body_reduced_density_matrix(s, orbitals):
#     r"""Constructs the one-body reduced density matrix from single-particle orbitals.

#     .. math:: \rho(x,x') = \sum^N_{n=1}\phi_n(x)\phi^*_n(x')

#     s: System
#         System object.
#     orbitals: np.ndarray
#         Array of normalised orbitals, indexed as orbitals[space,orbital_number].

#     returns:
#     n: np.ndarray
#         One body reduced density matrix.
#     """
#     p = np.zeros(shape=(s.x.shape[0], s.x.shape[0]), dtype=np.complex)
#     for i in range(s.NE):
#         p += np.tensordot(orbitals[:, i].conj(), orbitals[:, i], axes=0)
#     return p


# def total_energy(s, energies):
#     """Calculates the total energy from single particle energies.

#     s: System
#         System object.
#     energies: np.ndarray
#         Array of single particle energies.

#     returns:
#     E: float
#         Total energy.
#     """
#     E = np.sum(energies[: s.NE])
#     return E


# def ionisation_potential(s, energies):
#     """Calculates the ionisation potential from single particle energies.

#     s: System
#         System object.
#     energies: np.ndarray
#         Array of single particle energies.

#     returns:
#     ip: float
#         Ionisation potential.
#     """
#     ip = -energies[s.NE - 1]
#     return ip


# def electron_affinity(s, energies):
#     """Calculates the electron affinity from single particle energies.

#     s: System
#         System object.
#     energies: np.ndarray
#         Array of single particle energies.

#     returns:
#     ea: float
#         Electron affinity.
#     """
#     ea = -energies[s.NE]
#     return ea


# def single_particle_gap(s, energies):
#     """Calculates the single particle gap from single particle energies.

#     s: System
#         System object.
#     energies: np.ndarray
#         Array of single particle energies.

#     returns:
#     gap: float
#         Single particle gap.
#     """
#     gap = energies[s.NE] - energies[s.NE - 1]
#     return gap


# def propagate(s, orbitals, v_ptrb, times):
#     """Propigate a set of orbitals forward in time due to a local pertubation

#     s: System
#         System object.
#     orbitals: np.ndarray
#         Array of normalised orbitals, indexed as orbitals[space,orbital_number].
#     v_ptrb: np.ndarray
#         Local perturbing potential on the grid of x values.
#     times: np.ndarray
#         Grid of time values.

#     returns:
#     td_oribtals: nparray
#         Array of time dependent orbitals, indexed as orbitals[time,space,orbital_number]
#         Note: Returned orbitals is only the occupied orbitals, and so td_orbitals.shape[2] = s.NE.
#     """
#     K = kinetic_operator(s)
#     V = external_potential_operator(s) + np.diag(v_ptrb)
#     H = hamiltonian(s, K, V)
#     dt = times[1] - times[0]
#     U = spla.expm(-1.0j * dt * H)

#     td_oribtals = np.zeros(
#         shape=(times.shape[0], orbitals.shape[0], orbitals.shape[1]), dtype=np.complex
#     )
#     td_oribtals[0, :, :] = orbitals[:, :]

#     for i in range(orbitals.shape[1]):
#         for j, t in enumerate(times):
#             if j != 0:
#                 print(
#                     "iDEA.non_interacting.propagate: propagating orbital {0}/{1}, time = {2:.3f}/{3:.3f}".format(
#                         i + 1, orbitals.shape[1], t, np.max(times)
#                     ),
#                     end="\r",
#                 )
#                 td_oribtals[j, :, i] = np.dot(U, td_oribtals[j - 1, :, i])
#                 norm = npla.norm(td_oribtals[j, :, i]) * np.sqrt(s.dx)
#                 td_oribtals[j, :, i] /= norm
#         print()

#     return td_oribtals