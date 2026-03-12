// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title IncAgentEscrow
 * @notice Trustless USDC escrow for autonomous agent-to-agent trades.
 *
 * Flow:
 *   1. Buyer calls deposit() — USDC locked in contract
 *   2a. Seller delivers → Buyer calls release() — funds go to seller
 *   2b. Dispute → Either party calls dispute() — arbiter resolves
 *   2c. Timeout → Buyer calls refund() after deadline
 *
 * Supports Base, Arbitrum, Ethereum, Polygon (any EVM with USDC).
 */
contract IncAgentEscrow is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ── Types ────────────────────────────────────────────────────────

    enum EscrowStatus {
        EMPTY,        // 0 — slot unused
        FUNDED,       // 1 — buyer deposited, awaiting delivery
        RELEASED,     // 2 — funds sent to seller (trade complete)
        REFUNDED,     // 3 — funds returned to buyer (timeout / dispute)
        DISPUTED,     // 4 — dispute filed, awaiting arbiter
        RESOLVED      // 5 — arbiter resolved dispute
    }

    struct Escrow {
        address buyer;
        address seller;
        uint256 amount;          // USDC amount (6 decimals)
        uint256 deadline;        // Unix timestamp — auto-refund after this
        EscrowStatus status;
        bytes32 contractHash;    // SHA-256 of the off-chain contract terms
    }

    // ── State ────────────────────────────────────────────────────────

    IERC20 public immutable usdc;
    address public arbiter;      // Dispute resolver (initially deployer)
    uint256 public escrowCount;

    mapping(bytes32 => Escrow) public escrows;  // escrowId => Escrow

    uint256 public constant MIN_LOCK_SECONDS = 1 hours;
    uint256 public constant MAX_LOCK_SECONDS = 90 days;

    // ── Events ───────────────────────────────────────────────────────

    event Deposited(bytes32 indexed escrowId, address indexed buyer, address indexed seller, uint256 amount, uint256 deadline);
    event Released(bytes32 indexed escrowId, address indexed seller, uint256 amount);
    event Refunded(bytes32 indexed escrowId, address indexed buyer, uint256 amount);
    event Disputed(bytes32 indexed escrowId, address indexed filedBy);
    event DisputeResolved(bytes32 indexed escrowId, address recipient, uint256 buyerAmount, uint256 sellerAmount);
    event ArbiterChanged(address indexed oldArbiter, address indexed newArbiter);

    // ── Errors ───────────────────────────────────────────────────────

    error InvalidAmount();
    error InvalidDeadline();
    error InvalidAddress();
    error EscrowNotFunded();
    error EscrowAlreadyExists();
    error NotBuyer();
    error NotSeller();
    error NotParty();
    error NotArbiter();
    error DeadlineNotReached();
    error DeadlineReached();
    error NotDisputed();
    error InvalidSplit();

    // ── Constructor ──────────────────────────────────────────────────

    constructor(address _usdc, address _arbiter) {
        require(_usdc != address(0), "zero USDC address");
        require(_arbiter != address(0), "zero arbiter address");
        usdc = IERC20(_usdc);
        arbiter = _arbiter;
    }

    // ── Core Functions ───────────────────────────────────────────────

    /**
     * @notice Buyer deposits USDC into escrow.
     * @param escrowId Unique identifier (hash of trade details)
     * @param seller Seller's wallet address
     * @param amount USDC amount (6 decimals, e.g., 1000e6 = $1000)
     * @param lockSeconds How long seller has to deliver before auto-refund
     * @param contractHash SHA-256 hash of the off-chain contract terms
     */
    function deposit(
        bytes32 escrowId,
        address seller,
        uint256 amount,
        uint256 lockSeconds,
        bytes32 contractHash
    ) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        if (seller == address(0) || seller == msg.sender) revert InvalidAddress();
        if (lockSeconds < MIN_LOCK_SECONDS || lockSeconds > MAX_LOCK_SECONDS) revert InvalidDeadline();
        if (escrows[escrowId].status != EscrowStatus.EMPTY) revert EscrowAlreadyExists();

        uint256 deadline = block.timestamp + lockSeconds;

        escrows[escrowId] = Escrow({
            buyer: msg.sender,
            seller: seller,
            amount: amount,
            deadline: deadline,
            status: EscrowStatus.FUNDED,
            contractHash: contractHash
        });

        escrowCount++;

        // Transfer USDC from buyer to this contract
        usdc.safeTransferFrom(msg.sender, address(this), amount);

        emit Deposited(escrowId, msg.sender, seller, amount, deadline);
    }

    /**
     * @notice Buyer releases funds to seller after delivery verification.
     * @dev Only buyer can release. This is the happy path.
     */
    function release(bytes32 escrowId) external nonReentrant {
        Escrow storage e = escrows[escrowId];
        if (e.status != EscrowStatus.FUNDED) revert EscrowNotFunded();
        if (msg.sender != e.buyer) revert NotBuyer();

        e.status = EscrowStatus.RELEASED;

        usdc.safeTransfer(e.seller, e.amount);

        emit Released(escrowId, e.seller, e.amount);
    }

    /**
     * @notice Buyer reclaims funds after deadline (seller failed to deliver).
     * @dev Only buyer can refund, and only after deadline.
     */
    function refund(bytes32 escrowId) external nonReentrant {
        Escrow storage e = escrows[escrowId];
        if (e.status != EscrowStatus.FUNDED) revert EscrowNotFunded();
        if (msg.sender != e.buyer) revert NotBuyer();
        if (block.timestamp < e.deadline) revert DeadlineNotReached();

        e.status = EscrowStatus.REFUNDED;

        usdc.safeTransfer(e.buyer, e.amount);

        emit Refunded(escrowId, e.buyer, e.amount);
    }

    /**
     * @notice Either party files a dispute (before deadline).
     * @dev Freezes escrow until arbiter resolves.
     */
    function dispute(bytes32 escrowId) external {
        Escrow storage e = escrows[escrowId];
        if (e.status != EscrowStatus.FUNDED) revert EscrowNotFunded();
        if (msg.sender != e.buyer && msg.sender != e.seller) revert NotParty();

        e.status = EscrowStatus.DISPUTED;

        emit Disputed(escrowId, msg.sender);
    }

    /**
     * @notice Arbiter resolves a dispute by splitting funds.
     * @param buyerPct Percentage to buyer (0-100). Seller gets remainder.
     */
    function resolveDispute(
        bytes32 escrowId,
        uint256 buyerPct
    ) external nonReentrant {
        if (msg.sender != arbiter) revert NotArbiter();
        if (buyerPct > 100) revert InvalidSplit();

        Escrow storage e = escrows[escrowId];
        if (e.status != EscrowStatus.DISPUTED) revert NotDisputed();

        e.status = EscrowStatus.RESOLVED;

        uint256 buyerAmount = (e.amount * buyerPct) / 100;
        uint256 sellerAmount = e.amount - buyerAmount;

        if (buyerAmount > 0) {
            usdc.safeTransfer(e.buyer, buyerAmount);
        }
        if (sellerAmount > 0) {
            usdc.safeTransfer(e.seller, sellerAmount);
        }

        emit DisputeResolved(escrowId, msg.sender, buyerAmount, sellerAmount);
    }

    // ── Admin ────────────────────────────────────────────────────────

    /**
     * @notice Change the arbiter address. Only current arbiter can call.
     */
    function setArbiter(address newArbiter) external {
        if (msg.sender != arbiter) revert NotArbiter();
        if (newArbiter == address(0)) revert InvalidAddress();

        address old = arbiter;
        arbiter = newArbiter;

        emit ArbiterChanged(old, newArbiter);
    }

    // ── View Functions ───────────────────────────────────────────────

    function getEscrow(bytes32 escrowId) external view returns (Escrow memory) {
        return escrows[escrowId];
    }

    function isExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage e = escrows[escrowId];
        return e.status == EscrowStatus.FUNDED && block.timestamp >= e.deadline;
    }
}
